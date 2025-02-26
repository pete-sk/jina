import json
from argparse import Namespace
from typing import Dict, Optional, Tuple, Union, List

from .....hubble.helper import parse_hub_uri
from .....hubble.hubio import HubIO
from ....networking import K8sGrpcConnectionPool
from . import kubernetes_tools


def to_dns_name(name: str) -> str:
    """Converts the pod name to a dns compatible name.

    :param name: name of the pod
    :return: dns compatible name
    """
    return name.replace('/', '-').replace('_', '-').lower()


def get_deployment_yamls(
    name: str,
    namespace: str,
    image_name: str,
    container_cmd: str,
    container_args: str,
    replicas: int,
    pull_policy: str,
    jina_pod_name: str,
    pea_type: str,
    shard_id: Optional[int] = None,
    port_expose: Optional[int] = None,
    env: Optional[Dict] = None,
    gpus: Optional[Union[int, str]] = None,
    image_name_uses_before: Optional[str] = None,
    image_name_uses_after: Optional[str] = None,
    container_cmd_uses_before: Optional[str] = None,
    container_cmd_uses_after: Optional[str] = None,
    container_args_uses_before: Optional[str] = None,
    container_args_uses_after: Optional[str] = None,
) -> List[Dict]:
    """Get the yaml description of a service on Kubernetes

    :param name: name of the service and deployment
    :param namespace: k8s namespace of the service and deployment
    :param image_name: image for the k8s deployment
    :param container_cmd: command executed on the k8s pods
    :param container_args: arguments used for the k8s pod
    :param replicas: number of replicas
    :param pull_policy: pull policy used for fetching the Docker images from the registry.
    :param jina_pod_name: Name of the Jina Pod this deployment belongs to
    :param pea_type: type os this pea, can be gateway/head/worker
    :param shard_id: id of this shard, None if shards=1 or this is gateway/head
    :param port_expose: port which will be exposed by the deployed containers
    :param env: environment variables to be passed into configmap.
    :param gpus: number of gpus to use, for k8s requires you pass an int number, refers to the number of requested gpus.
    :param image_name_uses_before: image for uses_before container in the k8s deployment
    :param image_name_uses_after: image for uses_after container in the k8s deployment
    :param container_cmd_uses_before: command executed in the uses_before container on the k8s pods
    :param container_cmd_uses_after: command executed in the uses_after container on the k8s pods
    :param container_args_uses_before: arguments used for uses_before container on the k8s pod
    :param container_args_uses_after: arguments used for uses_after container on the k8s pod
    :return: Return a dictionary with all the yaml configuration needed for a deployment
    """
    # we can always assume the ports are the same for all executors since they run on different k8s pods
    # port expose can be defined by the user
    if not port_expose:
        port_expose = K8sGrpcConnectionPool.K8S_PORT_EXPOSE
    port_in = K8sGrpcConnectionPool.K8S_PORT_IN
    if name == 'gateway':
        port_ready_probe = port_expose
    else:
        port_ready_probe = port_in

    deployment_params = {
        'name': name,
        'namespace': namespace,
        'image': image_name,
        'replicas': replicas,
        'command': container_cmd,
        'args': container_args,
        'port_expose': port_expose,
        'port_in': port_in,
        'port_in_uses_before': K8sGrpcConnectionPool.K8S_PORT_USES_BEFORE,
        'port_in_uses_after': K8sGrpcConnectionPool.K8S_PORT_USES_AFTER,
        'args_uses_before': container_args_uses_before,
        'args_uses_after': container_args_uses_after,
        'command_uses_before': container_cmd_uses_before,
        'command_uses_after': container_cmd_uses_after,
        'image_uses_before': image_name_uses_before,
        'image_uses_after': image_name_uses_after,
        'pull_policy': pull_policy,
        'jina_pod_name': jina_pod_name,
        'shard_id': f'\"{shard_id}\"' if shard_id is not None else '\"\"',
        'pea_type': pea_type,
        'port_ready_probe': port_ready_probe,
    }

    if gpus:
        deployment_params['device_plugins'] = {'nvidia.com/gpu': gpus}

    template_name = 'deployment'

    if image_name_uses_before and image_name_uses_after:
        template_name = 'deployment-uses-before-after'
    elif image_name_uses_before:
        template_name = 'deployment-uses-before'
    elif image_name_uses_after:
        template_name = 'deployment-uses-after'

    yamls = [
        kubernetes_tools.get_yaml(
            'connection-pool-role',
            {
                'namespace': namespace,
            },
        ),
        kubernetes_tools.get_yaml(
            'connection-pool-role-binding',
            {
                'namespace': namespace,
            },
        ),
        kubernetes_tools.get_yaml(
            'configmap',
            {
                'name': name,
                'namespace': namespace,
                'data': env,
            },
        ),
        kubernetes_tools.get_yaml(
            'service',
            {
                'name': name,
                'target': name,
                'namespace': namespace,
                'port_expose': port_expose,
                'port_in': port_in,
                'type': 'ClusterIP',
            },
        ),
        kubernetes_tools.get_yaml(template_name, deployment_params),
    ]

    return yamls


def get_cli_params(
    arguments: Namespace, skip_list: Tuple[str] = (), port_in: Optional[int] = None
) -> str:
    """Get cli parameters based on the arguments.

    :param arguments: arguments where the cli parameters are generated from
    :param skip_list: list of arguments which should be ignored
    :param port_in: overwrite port_in with the provided value if set

    :return: string which contains all cli parameters
    """
    arguments.host = '0.0.0.0'
    skip_attributes = [
        'uses',  # set manually
        'uses_with',  # set manually
        'runtime_cls',  # set manually
        'workspace',
        'log_config',
        'polling_type',
        'uses_after',
        'uses_before',
        'replicas',
    ] + list(skip_list)
    if port_in:
        arguments.port_in = port_in
    arg_list = [
        [attribute, attribute.replace('_', '-'), value]
        for attribute, value in arguments.__dict__.items()
    ]
    cli_args = []
    for attribute, cli_attribute, value in arg_list:
        # TODO: This should not be here, its a workaround for our parser design with boolean values
        if attribute == 'k8s_connection_pool' and not value:
            cli_args.append(f'"--k8s-disable-connection-pool"')
        if attribute in skip_attributes:
            continue
        if type(value) == bool and value:
            cli_args.append(f'"--{cli_attribute}"')
        elif type(value) != bool:
            if value is not None:
                value = str(value)
                value = value.replace('\'', '').replace('"', '\\"')
                cli_args.append(f'"--{cli_attribute}", "{value}"')

    cli_string = ', '.join(cli_args)
    return cli_string


def get_image_name(uses: str) -> str:
    """The image can be provided in different formats by the user.
    This function converts it to an image name which can be understood by k8s.
    It uses the Hub api to get the image name and the latest tag on Docker Hub.
    :param uses: image name

    :return: normalized image name
    """
    try:
        scheme, name, tag, secret = parse_hub_uri(uses)
        meta_data, _ = HubIO.fetch_meta(name, tag, secret=secret, force=True)
        image_name = meta_data.image_name
        return image_name
    except Exception:
        if uses.startswith('docker'):
            # docker:// is a valid requirement and user may want to put its own image
            return uses.replace('docker://', '')
        raise


def dictionary_to_cli_param(dictionary) -> str:
    """Convert the dictionary into a string to pass it as argument in k8s.
    :param dictionary: dictionary which has to be passed as argument in k8s.

    :return: string representation of the dictionary
    """
    return json.dumps(dictionary).replace('"', '\\"') if dictionary else ""
