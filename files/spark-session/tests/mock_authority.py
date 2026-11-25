"""python-dbusmock template: a fake polkit authority (org.freedesktop.PolicyKit1).

It accepts the agent's registration and records the calls the tests look at
(RegisterAuthenticationAgent, AuthenticationAgentResponse2). It decides nothing: the test plays
the authority by calling the agent's BeginAuthentication itself."""

import dbus

BUS_NAME = 'org.freedesktop.PolicyKit1'
MAIN_OBJ = '/org/freedesktop/PolicyKit1/Authority'
MAIN_IFACE = 'org.freedesktop.PolicyKit1.Authority'
SYSTEM_BUS = True

SUBJECT = '(sa{sv})'


def load(mock, parameters):
    mock.AddMethods(MAIN_IFACE, [
        ('RegisterAuthenticationAgent', f'{SUBJECT}ss', '', ''),
        ('RegisterAuthenticationAgentWithOptions', f'{SUBJECT}ssa{{sv}}', '', ''),
        ('UnregisterAuthenticationAgent', f'{SUBJECT}s', '', ''),
        ('AuthenticationAgentResponse', f's{SUBJECT}', '', ''),
        ('AuthenticationAgentResponse2', f'us{SUBJECT}', '', ''),
    ])
    mock.AddProperties(MAIN_IFACE, dbus.Dictionary({
        'BackendName': 'mock', 'BackendVersion': '0', 'BackendFeatures': dbus.UInt32(0),
    }, signature='sv'))
