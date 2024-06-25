
IXIA_HOST = "10.137.91.199"
IXIA_PORT = 12031

ESR_MULTI_VRF_CONFIG = "esr_multi_vrf.ixncfg"
ESR_MULTI_VRF_ECMP_CONFIG = "esr_multi_vrf_ecmp.ixncfg"
ESR_ECMP_CONFIG = "esr_ecmp_04.ixncfg"
ESR_MIRROR_CONFIG = "esr_mirror.ixncfg"
ESR_2K_POLICY_CONFIG = "esr_te_policy.ixncfg"
ESR_SID_REMARKING_CONFIG = "esr_sid_remarking.ixncfg"
ESR_IPV4_IPV6_POLICY_CONFIG = "ip_ipv6_te_policy.ixncfg"

# IXIA_PORT connected to 179
PORT_NAME_1 = "1/1/15"
PORT_NAME_2 = "1/1/16"

# IXIA_PORT connected to 178
PORT_NAME_3 = "1/1/21"
PORT_NAME_4 = "1/1/22"

# Scalable Sources
DEVICE_1_IPV4            ="/api/v1/sessions/1/ixnetwork/topology/1/deviceGroup/1/ethernet/1/ipv4/1" # 1/1/15
DEVICE_2_IPV4            ="/api/v1/sessions/1/ixnetwork/topology/2/deviceGroup/1/ethernet/1/ipv4/1" # 1/1/16

# Scalable Destinations
DEVICE_3_IPV4_PREFIX_POOL="/api/v1/sessions/1/ixnetwork/topology/3/deviceGroup/1/networkGroup/1/ipv4PrefixPools/1" # 1/1/21
DEVICE_4_IPV4_PREFIX_POOL="/api/v1/sessions/1/ixnetwork/topology/4/deviceGroup/1/networkGroup/1/ipv4PrefixPools/1" # 1/1/22


TOPOLOGY_3 = "Topology 3"
DEVICE_GROUP_3 = "Device Group 3"
NETWORK_GROUP_1 = "Network Group 1"
IPV4_PREFIX_POOL_1 = "Basic IPv4 Addresses 1"
BGP_IP_ROUTE_PROPERTY_1 = "BGP IP Route Range 1"

TOPOLOGY_4 = "Topology 4"
DEVICE_GROUP_4 = "Device Group 4"
NETWORK_GROUP_2 = "Network Group 2"
IPV4_PREFIX_POOL_2 = "Basic IPv4 Addresses 2"
BGP_IP_ROUTE_PROPERTY_2 = "BGP IP Route Range 2"

# Traffic items
VRF_TRAFFIC_NAME = "t-g1-1"
SPECIFIC_VRF_TRAFFIC_NAME = "Specific-Vrf_traffic"
ECMP_TRAFFIC_NAME = "traffic_ecmp"
TRAFFIC_MIRROR_V4 = "TI-IPv4"
TRAFFIC_MIRROR_V6 = "TI-IPv6"
TRAFFIC_MIRROR_ULECMP = "ul-ecmp"
TRAFFIC_1K_TE_POLICY = "TE-1k"
TRAFFIC_2K_TE_POLICY = "TE-2K"
TRAFFIC_SID_REMARKING_V4_SUCCESS = "Traffic_SID_remarking_v4_success"
TRAFFIC_SID_REMARKING_V4_FAIL = "Traffic_SID_remarking_v4_fail"
TRAFFIC_SID_REMARKING_V6_SUCCESS = "Traffic_SID_remarking_v6_success"
TRAFFIC_SID_REMARKING_V6_FAIL = "Traffic_SID_remarking_v6_fail"
TRAFFIC_IPV4_TE_POLICY = "TE-IPv4"
TRAFFIC_IPV6_TE_POLICY = "TE-IPv6"