from spytest import st
import apis.system.basic as basic_obj

def check_wpa_supplicant_process(dut, ctrl_port_name):
    command = "ps aux | grep -w 'wpa_supplicant' | grep -w '{}' | grep -v 'grep'".format(ctrl_port_name)
    output = st.show(dut, command, skip_tmpl=True)
    if "wpa_supplicant" in output:
        return True
    else:
        return False

def create_macsec_profile(dut, profile_name, cipher_suite, primary_cak, primary_ckn, priority = 0, policy = "security", send_sci = "true"):
    command = "macsec profile {} cipher_suite {} primary_ckn {} primary_cak {} priority {} policy {} send_sci {}".format(
                    profile_name, cipher_suite, primary_ckn, primary_cak, priority, policy, send_sci)
    output =  st.config(dut, command, type='alicli', skip_error_check=True)
    if "Error" in output:
        return False
    return True

def delete_macsec_profile(dut, profile_name):
    command = "no macsec profile {}".format(profile_name)
    output =  st.config(dut, command, type='alicli', skip_error_check=True)
    if "Error" in output:
        return False
    return True

def enable_macsec_port(dut, port, profile_name):
    command = "macsec port {} {}".format(port, profile_name)
    output = st.config(dut, command, type='alicli', skip_error_check=True)
    if "Error" in output:
        return False
    return True

def disable_macsec_port(dut, port):
    command = "no macsec port {}".format(port)
    output = st.config(dut, command, type='alicli', skip_error_check=True)
    if "Error" in output:
        return False
    return True

def show_macsec_connections(dut, port, skiptmpl=True):
    command = "cli -c 'no page' -c 'show macsec connections interface {}'".format(port)
    return st.show(dut, command, skip_tmpl=skiptmpl, skip_error_check=True)

def show_macsec_mka(dut, port):
    command = "cli -c 'no page' -c 'show macsec mka interface {}'".format(port)
    return st.show(dut, command, skip_tmpl=True, skip_error_check=True)

def show_macsec_mib(dut, port):
    command = "cli -c 'no page' -c 'show macsec mib interface {}'".format(port)
    return st.show(dut, command, skip_tmpl=True, skip_error_check=True)

def show_macsec_statistics(dut, port):
    command = "cli -c 'no page' -c 'show macsec statistics interface {}'".format(port)
    return st.show(dut, command, skip_tmpl=True, skip_error_check=True)

def show_macsec_profiles(dut):
    command = "cli -c 'no page' -c 'show macsec profiles'"
    return st.show(dut, command, skip_tmpl=True, skip_error_check=True)