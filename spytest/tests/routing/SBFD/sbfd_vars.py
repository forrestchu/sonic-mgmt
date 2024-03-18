from spytest.dicts import SpyTestDict

data = SpyTestDict()

data['policy_sbfd'] = {
    'policy color 1 endpoint 2000::59':
        ['peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 1 sidlist )'
        ],
    'policy color 2 endpoint 2000::59':
        ['peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 2 sidlist )'
        ],
    'policy color 3 endpoint 2000::59':
        ['peer 20.20.20.58 local-address 20.20.20.58 (endpoint 20.20.20.58 color 3 sidlist sl5_ipv4)',
         'peer 20.20.20.58 local-address 20.20.20.58 (endpoint 20.20.20.58 color 3 sidlist sl7_ipv4)'
        ],
    'policy color 4 endpoint 2000::59':
        ['peer 2000::58 local-address 2000::58 (endpoint 2000::58 color 4 sidlist sl6_ipv6)',
         'peer 2000::58 local-address 2000::58 (endpoint 2000::58 color 4 sidlist sl8_ipv6)'
        ],
    'policy color 6 endpoint 2000::59':
        ['peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 6 sidlist sl5_ipv4)',
         'peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 6 sidlist sl7_ipv4)'
        ],
    'policy color 7 endpoint 2000::59':
        ['peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 7 sidlist sl6_ipv6)',
         'peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 7 sidlist sl8_ipv6)'
        ],
    'policy color 8 endpoint 2000::59':
        ['peer 20.20.20.58 local-address 20.20.20.58 (endpoint 20.20.20.58 color 8 sidlist sl5_ipv4)',
         'peer 20.20.20.58 local-address 20.20.20.58 (endpoint 20.20.20.58 color 8 sidlist sl7_ipv4)'
        ],
    'policy color 9 endpoint 2000::59':
        ['peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 9 sidlist sl9_sbfd)',
         'peer 2000::59 local-address 2000::58 (endpoint 2000::59 color 9 sidlist sla_sbfd)'
        ]
} 

