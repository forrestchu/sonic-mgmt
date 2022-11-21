
from ixia_lib import IxiaController


ixia_controller = IxiaController()

def ixia_check_port_rx_frame(port_name, rx_count):
    port_stats = ixia_controller.get_port_statistics(port_name)
    if port_stats is None:
        return False

    if port_stats['Valid Frames Rx.'] == rx_count:
        return True
    return False


def ixia_load_config(config_file):
    ixia_controller.load_config(config_file)


def ixia_get_traffic_item():
    traffic_items = ixia_controller.get_traffic_items()
    return traffic_items[0]


def ixia_start_traffic_item(traffic_item):
    ixia_controller.start_stateless_traffic(traffic_item)

def ixia_stop_traffic_item(traffic_item):
    ixia_controller.stop_stateless_traffic(traffic_item)


