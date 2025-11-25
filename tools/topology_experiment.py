#!/usr/bin/env python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Node
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import sys
import argparse

class GameTopo(Topo):
    """
    Simple topology: server <-> switch <-> player
    
    This topology creates a basic network setup for CGReplay experiments:
    - Server host (10.0.0.1) streams video frames to the player
    - Player host (10.0.0.2) receives and processes video frames
    - Single switch (s1) provides L2 connectivity with configurable bandwidth
    - Both links use the same bandwidth to simulate network constraints
    
    Designed for testing cloud gaming applications under controlled
    network conditions with adjustable bandwidth limitations.
    """
    def __init__(self, bandwidth=2, **opts):
        Topo.__init__(self, **opts)
        
        # Add switch
        switch = self.addSwitch('s1')
        
        # Add server and player hosts
        server = self.addHost('server', ip='10.0.0.1/24')
        player = self.addHost('player', ip='10.0.0.2/24')
        
        # Add links with specified bandwidth
        self.addLink(server, switch, bw=bandwidth)
        self.addLink(switch, player, bw=bandwidth)

def create_topology(bandwidth=2):
    """
    Create and run the game topology
    """
    topo = GameTopo(bandwidth=bandwidth)
    net = Mininet(topo=topo, link=TCLink, controller=None)
    
    info('*** Starting network\n')
    net.start()
    
    # Configure interface names
    info('*** Configuring interface names\n')
    net.get('server').cmd('ip link set server-eth0 name server-eth0 2>/dev/null || true')
    net.get('player').cmd('ip link set player-eth0 name player-eth0 2>/dev/null || true')
    
    # Add flow rule for automatic MAC learning
    info('*** Configuring switch for automatic MAC learning\n')
    net.get('s1').cmd('ovs-ofctl add-flow s1 action=normal')
    
    info('*** Network configuration:\n')
    info('*** Server: 10.0.0.1 (server-eth0)\n')
    info('*** Player: 10.0.0.2 (player-eth0)\n')
    info('*** Switch: s1 (automatic MAC learning)\n')
    info('*** Link bandwidth: %d Mbps\n' % bandwidth)
    
    info('*** Opening xterm terminals with virtual environment\n')
    # Create temporary bashrc files that source the virtual environment
    server_bashrc = '/tmp/server_bashrc'
    player_bashrc = '/tmp/player_bashrc'
    
    # Player bashrc: activate venv and run cg_gamer1.py first
    net.get('player').cmd('echo "source /home/ariel/venvs/CGSynth/bin/activate" > %s' % player_bashrc)
    net.get('player').cmd('echo "export PS1=\'(CGSynth) \\u@\\h:\\w\\$ \'" >> %s' % player_bashrc)
    net.get('player').cmd('echo "cd /home/ariel/git/CGSynth/CGReplay/player" >> %s' % player_bashrc)
    net.get('player').cmd('echo "echo Starting CG Player..." >> %s' % player_bashrc)
    net.get('player').cmd('echo "python cg_gamer1.py" >> %s' % player_bashrc)
    
    # Server bashrc: activate venv, wait 5 seconds, then run cg_server1.py
    net.get('server').cmd('echo "source /home/ariel/venvs/CGSynth/bin/activate" > %s' % server_bashrc)
    net.get('server').cmd('echo "export PS1=\'(CGSynth) \\u@\\h:\\w\\$ \'" >> %s' % server_bashrc)
    net.get('server').cmd('echo "cd /home/ariel/git/CGSynth/CGReplay/server" >> %s' % server_bashrc)
    net.get('server').cmd('echo "echo Starting CG Server in 5 seconds..." >> %s' % server_bashrc)
    net.get('server').cmd('echo "sleep 5" >> %s' % server_bashrc)
    net.get('server').cmd('echo "echo Starting CG Server now..." >> %s' % server_bashrc)
    net.get('server').cmd('echo "python cg_server1.py" >> %s' % server_bashrc)
    
    # Open player xterm first (starts immediately)
    player_xterm_output = net.get('player').cmd('xterm -e "bash --rcfile %s" &' % player_bashrc)
    # Open server xterm second (will wait 5 seconds before starting)
    server_xterm_output = net.get('server').cmd('xterm -e "bash --rcfile %s" &' % server_bashrc)
    
    # Extract actual PID from output (format: "[1] 34479")
    server_xterm = server_xterm_output.strip().split()[-1] if server_xterm_output.strip() else ""
    player_xterm = player_xterm_output.strip().split()[-1] if player_xterm_output.strip() else ""
    
    info('*** Server xterm PID: %s\n' % server_xterm)
    info('*** Player xterm PID: %s\n' % player_xterm)
    
    info('*** Testing connectivity\n')
    net.pingAll()
    
    info('*** Running CLI\n')
    try:
        CLI(net)
    finally:
        # Clean up xterm processes and temporary files
        info('*** Cleaning up xterm processes\n')
        if server_xterm.strip():
            net.get('server').cmd('kill %s 2>/dev/null || true' % server_xterm.strip())
        if player_xterm.strip():
            net.get('player').cmd('kill %s 2>/dev/null || true' % player_xterm.strip())
        
        info('*** Cleaning up temporary files\n')
        net.get('server').cmd('rm -f %s 2>/dev/null || true' % server_bashrc)
        net.get('player').cmd('rm -f %s 2>/dev/null || true' % player_bashrc)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CGReplay Mininet Topology')
    parser.add_argument('--bandwidth', '-b', type=int, default=10, 
                       help='Link bandwidth in Mbps (default: 10)')
    args = parser.parse_args()
    
    setLogLevel('info')
    create_topology(bandwidth=args.bandwidth)
