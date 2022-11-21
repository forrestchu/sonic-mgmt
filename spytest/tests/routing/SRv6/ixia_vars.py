
IXIA_HOST = "10.97.244.219"
IXIA_PORT = 12020

IXIA_CONFIG_FILE = "esr_multi_vrf.ixncfg"


# IXIA_PORT connected to 179
PORT_NAME_1 = "1/1/15"
PORT_NAME_2 = "1/1/16"

# IXIA_PORT connected to 178
PORT_NAME_3 = "1/1/21"
PORT_NAME_4 = "1/1/22"

# Scalable Sources
DEVICE_1_IPV4            ="/api/v1/sessions/1/ixnetwork/topology/1/deviceGroup/1/ethernet/1/ipv4/1"
DEVICE_2_IPV4            ="/api/v1/sessions/1/ixnetwork/topology/2/deviceGroup/1/ethernet/1/ipv4/1"

# Scalable Destinations
DEVICE_3_IPV4_PREFIX_POOL="/api/v1/sessions/1/ixnetwork/topology/3/deviceGroup/1/networkGroup/1/ipv4PrefixPools/1"
DEVICE_4_IPV4_PREFIX_POOL="/api/v1/sessions/1/ixnetwork/topology/4/deviceGroup/1/networkGroup/1/ipv4PrefixPools/1"

