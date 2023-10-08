from spytest.dicts import SpyTestDict

data = SpyTestDict()

data['policy_sbfd'] = {
    'policy color 1 endpoint 2000::59':
        ['peer 20.20.20.58 (endpoint 20.20.20.58 color 1 sidlist sl1_ipv4) local-address 20.20.20.58'
        ],
    'policy color 2 endpoint 2000::59':
        ['peer 2000::58 (endpoint 2000::58 color 2 sidlist sl2_ipv6) local-address 2000::58'
        ],
    'policy color 3 endpoint 2000::59':
        ['peer 20.20.20.58 (endpoint 20.20.20.58 color 3 sidlist sl1_ipv4) local-address 20.20.20.58',
         'peer 20.20.20.58 (endpoint 20.20.20.58 color 3 sidlist sl3_ipv4) local-address 20.20.20.58'
        ],
    'policy color 4 endpoint 2000::59':
        ['peer 2000::58 (endpoint 2000::58 color 4 sidlist sl2_ipv6) local-address 2000::58',
         'peer 2000::58 (endpoint 2000::58 color 4 sidlist sl4_ipv6) local-address 2000::58'
        ],
    'policy color 6 endpoint 2000::59':
        ['peer 20.20.20.58 (endpoint 20.20.20.58 color 6 sidlist sl1_ipv4) local-address 20.20.20.58',
         'peer 20.20.20.58 (endpoint 20.20.20.58 color 6 sidlist sl3_ipv4) local-address 20.20.20.58'
        ],
    'policy color 7 endpoint 2000::59':
        ['peer 2000::58 (endpoint 2000::58 color 7 sidlist sl2_ipv6) local-address 2000::58',
         'peer 2000::58 (endpoint 2000::58 color 7 sidlist sl4_ipv6) local-address 2000::58'
        ],
    'policy color 8 endpoint 2000::59':
        ['peer 20.20.20.58 (endpoint 20.20.20.58 color 8 sidlist sl1_ipv4) local-address 20.20.20.58',
         'peer 20.20.20.58 (endpoint 20.20.20.58 color 8 sidlist sl5_ipv4) local-address 20.20.20.58',
         'peer 20.20.20.58 (endpoint 20.20.20.58 color 8 sidlist sl7_ipv4) local-address 20.20.20.58'
        ],
    'policy color 9 endpoint 2000::59':
        ['peer 2000::58 (endpoint 2000::58 color 9 sidlist sl9_sbfd) local-address 2000::58',
         'peer 2000::58 (endpoint 2000::58 color 9 sidlist sla_sbfd) local-address 2000::58'
        ]
} 

