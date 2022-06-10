import pytest
import re

from spytest import st, tgapi, SpyTestDict
import apis.macsec.macsec as macsec_api

data = SpyTestDict()
data.port = "Ethernet1"
data.profile_name = "GCM-128"
data.profile_name_2 = "GCM-128-2"
data.cipher_suite = "GCM-AES-128"
data.primary_ckn = "3007"
data.primary_cak = "00112233445566778899001122334455"
data.primary_cak_64 = "0011223344556677889900112233445500112233445566778899001122334455"

@pytest.fixture(scope="module", autouse=True)
def macsec_module_hooks(request):
    global vars
    vars = st.ensure_min_topology("D1")

def test_macsec_simple_config():
    # 1. create profile
    st.log("create macsec profile {}".format(data.profile_name))
    ret = macsec_api.create_macsec_profile(vars.D1, data.profile_name, data.cipher_suite, data.primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name))

    output = macsec_api.show_macsec_profiles(vars.D1)
    if data.profile_name not in output:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name))

    # 2. enable port
    st.log("enable macsec port {} with profile {}".format(data.port, data.profile_name))
    ret = macsec_api.enable_macsec_port(vars.D1, data.port, data.profile_name)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(data.port, data.profile_name))

    st.wait(3)

    # 3. check wpa_supplicant
    ret = macsec_api.check_wpa_supplicant_process(vars.D1, data.port)
    if not ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't started.".format(data.port))

    # 4. delete profile, expect fail
    ret = macsec_api.delete_macsec_profile(vars.D1, data.profile_name)
    if ret:
        st.report_fail("The macsec profile {} should not be deleted.".format(data.profile_name))

    # 5. create another profile
    st.log("create macsec profile {}".format(data.profile_name_2))
    ret = macsec_api.create_macsec_profile(vars.D1, data.profile_name_2, data.cipher_suite, data.primary_cak, data.primary_ckn)
    if not ret:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name_2))

    output = macsec_api.show_macsec_profiles(vars.D1)
    if data.profile_name_2 not in output:
        st.report_fail("Failed to create macsec profile {}".format(data.profile_name_2))

    # 6. replace profile
    ret = macsec_api.enable_macsec_port(vars.D1, data.port, data.profile_name_2)
    if not ret:
        st.report_fail("Failed to enable macsec port {} with profile {}".format(data.port, data.profile_name_2))

    # 7. disable macsec port
    ret = macsec_api.disable_macsec_port(vars.D1, data.port)
    if not ret:
        st.report_fail("Failed to disable macsec port {}".format(data.port))

    # 8. check wpa_supplicant, should not exist
    st.wait(3)
    ret = macsec_api.check_wpa_supplicant_process(vars.D1, data.port)
    if ret:
        st.report_fail("The wpa_supplicant for the port {} wasn't stopped.".format(data.port))

    # 9. delete profile
    ret = macsec_api.delete_macsec_profile(vars.D1, data.profile_name_2)
    if not ret:
        st.report_fail("Failed to delete macsec profile {}".format(data.profile_name_2))

    ret = macsec_api.delete_macsec_profile(vars.D1, data.profile_name)
    if not ret:
        st.report_fail("Failed to delete macsec profile {}".format(data.profile_name))

    st.report_pass("test_case_passed")
