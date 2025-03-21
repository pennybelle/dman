import logging
import struct
import socket
import asyncio
import os
import toml
import datetime

# from dman import server_states
from modules.serverstate import ServerState

log = logging.getLogger(__name__)


# RCON Constants
SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RCONClient:
    """Simple RCON client implementation for DayZ servers"""

    def __init__(self, port, password, host="127.0.0.1"):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
        self.authenticated = False
        self.request_id = 0

    async def connect(self):
        """Connect to the RCON server"""
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # 10 second timeout
            self.socket.connect((self.host, self.port))
            log.info(f"Connected to RCON at {self.host}:{self.port}")

            # Authenticate
            result = await self.authenticate()
            if not result:
                log.error("RCON authentication failed")
                self.socket.close()
                return False

            self.authenticated = True
            return True
        except Exception as e:
            log.error(f"RCON connection error: {e}")
            if self.socket:
                self.socket.close()
            return False

    async def authenticate(self):
        """Authenticate with the RCON server using the provided password"""
        if not self.socket:
            return False

        self.request_id += 1
        request_id = self.request_id

        # Send auth packet
        packet = self._build_packet(request_id, SERVERDATA_AUTH, self.password)
        self.socket.send(packet)

        # Receive response
        response = await self._receive_response()

        # Check if authentication was successful
        if (
            response
            and response.get("type") == SERVERDATA_AUTH_RESPONSE
            and response.get("id") == request_id
        ):
            log.info("RCON authentication successful")
            return True
        else:
            log.error("RCON authentication failed")
            return False

    async def send_command(self, command):
        """Send a command to the RCON server and get the response"""
        if not self.socket or not self.authenticated:
            log.error("RCON not connected or not authenticated")
            return None

        self.request_id += 1
        request_id = self.request_id

        # Send command packet
        packet = self._build_packet(request_id, SERVERDATA_EXECCOMMAND, command)
        self.socket.send(packet)

        # Receive response
        response = await self._receive_response()

        if response and response.get("id") == request_id:
            return response.get("body", "")
        return None

    async def _receive_response(self):
        """Receive and parse RCON response packet"""
        try:
            # First get the packet size
            size_data = self.socket.recv(4)
            if not size_data:
                return None

            size = struct.unpack("<I", size_data)[0]

            # Now get the actual packet
            packet_data = b""
            remaining = size
            while remaining > 0:
                chunk = self.socket.recv(remaining)
                if not chunk:
                    break
                packet_data += chunk
                remaining -= len(chunk)

            # Parse the packet
            if (
                len(packet_data) >= 8
            ):  # Minimum packet size (id + type + empty string + null terminator)
                response_id = struct.unpack("<I", packet_data[0:4])[0]
                response_type = struct.unpack("<I", packet_data[4:8])[0]

                # Extract the response body (null-terminated string)
                body = ""
                if len(packet_data) > 8:
                    body = packet_data[8:-2].decode("utf-8", errors="replace")

                return {"id": response_id, "type": response_type, "body": body}
        except Exception as e:
            log.error(f"Error receiving RCON response: {e}")

        return None

    def _build_packet(self, request_id, packet_type, body):
        """Build an RCON packet"""
        # Convert body to bytes if it's a string
        if isinstance(body, str):
            body = body.encode("utf-8")

        # Add null terminators
        body = body + b"\x00\x00"

        # Calculate packet size (excluding the size field itself)
        size = 4 + 4 + len(body)  # id + type + body with null terminators

        # Build the packet
        packet = struct.pack("<I", size)  # Size
        packet += struct.pack("<I", request_id)  # Request ID
        packet += struct.pack("<I", packet_type)  # Packet Type
        packet += body  # Body with null terminators

        return packet

    def close(self):
        """Close the RCON connection"""
        if self.socket:
            try:
                self.socket.close()
                log.info("RCON connection closed")
            except Exception as e:
                log.error(f"Error closing RCON connection: {e}")
            finally:
                self.socket = None
                self.authenticated = False


async def kick_all_and_restart(
    server_states,
    instance_name,
    rcon_port,
    rcon_password,
    host="127.0.0.1",
    restart_delay=60,
):
    """
    Kick all players and restart a DayZ server using RCON

    Args:
        instance_name: Name of the server instance
        host: RCON host address (default 127.0.0.1)
        rcon_port: RCON port (default is game port + 1)
        rcon_password: RCON password
        restart_delay: Delay in seconds before server restart (default 60)

    Returns:
        bool: True if successful, False otherwise
    """
    if not rcon_password:
        log.error(f"[{instance_name}] No RCON password provided")
        return False

    # Get the server info from server_states
    if instance_name not in server_states:
        log.error(f"[{instance_name}] Server instance not found in server_states")
        return False

    # server = server_states[instance_name]
    # game_port = server.get("rcon_port")

    # # If no RCON port specified, use game port + 1 (DayZ default)
    # if not rcon_port and game_port:
    #     rcon_port = game_port + 1

    if not rcon_port:
        log.error(f"[{instance_name}] Could not determine RCON port")
        return False

    log.info(
        f"[{instance_name}] Starting kick all and restart procedure via RCON on port {rcon_port}"
    )

    # Create RCON client
    rcon = RCONClient(port=rcon_port, password=rcon_password, host=host)

    try:
        # Connect to RCON
        connected = await rcon.connect()
        if not connected:
            log.error(f"[{instance_name}] Failed to connect to RCON")
            return False

        # Announce server restart
        message = f"SERVER RESTART IN {restart_delay} SECONDS. YOU WILL BE KICKED."
        log.info(f"[{instance_name}] Broadcasting restart message: {message}")
        await rcon.send_command(f'say -1 "{message}"')

        # Get list of players
        log.info(f"[{instance_name}] Getting player list")
        players_response = await rcon.send_command("players")

        if not players_response:
            log.warning(
                f"[{instance_name}] Could not get player list, assuming no players"
            )
            players = []
        else:
            # Parse player list
            players = []
            # Typical format:
            # Players on server:
            # [#] [ID] [Name]
            # 0   12   PlayerName

            lines = players_response.strip().split("\n")
            if len(lines) > 2:  # Header lines + at least one player
                for i in range(2, len(lines)):
                    parts = lines[i].strip().split()
                    if len(parts) >= 3:
                        try:
                            player_id = int(parts[1])
                            player_name = " ".join(parts[2:])
                            players.append((player_id, player_name))
                        except (ValueError, IndexError):
                            log.warning(
                                f"[{instance_name}] Could not parse player line: {lines[i]}"
                            )

        # If players found, kick them all
        if players:
            log.info(f"[{instance_name}] Kicking {len(players)} players")
            for player_id, player_name in players:
                kick_message = (
                    "Server is restarting. Please reconnect in a few minutes."
                )
                log.info(
                    f"[{instance_name}] Kicking player {player_name} (ID: {player_id})"
                )

                kick_response = await rcon.send_command(
                    f'kick {player_id} "{kick_message}"'
                )
                log.debug(f"[{instance_name}] Kick response: {kick_response}")

                # Small delay between kicks to avoid overloading the server
                await asyncio.sleep(0.5)
        else:
            log.info(f"[{instance_name}] No players to kick")

        # Wait for the specified delay before restart
        log.info(f"[{instance_name}] Waiting {restart_delay} seconds before restart")
        for i in range(restart_delay, 0, -10):
            if i <= 30:  # More frequent updates in the last 30 seconds
                step = 5
            else:
                step = 10

            # Announce time remaining if more than one step left
            if i > step:
                await rcon.send_command(f'say -1 "SERVER RESTARTING IN {i} SECONDS"')
                log.info(f"[{instance_name}] Restart in {i} seconds")
                await asyncio.sleep(step)

        # Final announcement
        await rcon.send_command('say -1 "SERVER RESTARTING NOW"')
        log.info(f"[{instance_name}] Executing restart command")

        # Send restart command
        restart_response = await rcon.send_command("#shutdown")
        log.info(f"[{instance_name}] Restart response: {restart_response}")

        # Close RCON connection
        rcon.close()

        # Update server state
        if instance_name in server_states:
            server_states[instance_name]["state"] = ServerState.STOPPED
            server_states[instance_name]["events"].append(
                {
                    "timestamp": datetime.datetime.now(),
                    "state": ServerState.STOPPED.value,
                    "message": "Server restarted via RCON",
                }
            )

        log.info(f"[{instance_name}] Kick all and restart completed successfully")
        return True

    except Exception as e:
        log.error(f"[{instance_name}] Error during kick all and restart: {e}")
        if rcon:
            rcon.close()
        return False


# Example function to start the restart process for a specific server
async def schedule_server_restart(
    server_states, app_path, instance_name, restart_delay=60, warning_time=300
):
    """
    Schedule a server restart with warnings

    Args:
        instance_name: Name of the server instance
        restart_delay: Time in seconds to wait between kicking players and restart (default 60)
        warning_time: Time in seconds to warn players before kicking begins (default 300, 5 minutes)
    """
    if instance_name not in server_states:
        log.error(f"Cannot restart unknown server: {instance_name}")
        return

    # Get server config to find RCON password
    server_config_path = os.path.join(app_path, "servers", instance_name, "server.toml")

    try:
        server_config = toml.load(server_config_path)
        rcon_port = server_config.get("server", {}).get("rcon", {}).get("port")
        rcon_password = server_config.get("server", {}).get("rcon", {}).get("password")

        if not rcon_password:
            log.error(
                f"[{instance_name}] No RCON password found in server configuration"
            )
            return

        # Send warning messages at intervals
        rcon = RCONClient(host="127.0.0.1", port=rcon_port, password=rcon_password)

        connected = await rcon.connect()
        if not connected:
            log.error(f"[{instance_name}] Failed to connect to RCON for warnings")
            return

        # Warnings at various intervals
        warning_intervals = [warning_time, 180, 120, 60, 30]

        for interval in warning_intervals:
            if interval <= warning_time:
                minutes = interval // 60
                message = (
                    f"SERVER RESTART IN {minutes} MINUTE{'S' if minutes > 1 else ''}"
                )
                log.info(f"[{instance_name}] Warning: {message}")
                await rcon.send_command(f'say -1 "{message}"')

                # Wait until next warning interval
                next_index = warning_intervals.index(interval) + 1
                if next_index < len(warning_intervals):
                    wait_time = interval - warning_intervals[next_index]
                    await asyncio.sleep(wait_time)
                else:
                    # Last warning, wait until restart
                    await asyncio.sleep(interval - restart_delay)

        rcon.close()

        # Execute kick all and restart
        success = await kick_all_and_restart(
            server_states=server_states,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            instance_name=instance_name,
            restart_delay=restart_delay,
        )

        if not success:
            log.error(f"[{instance_name}] Failed to restart server via RCON")

    except Exception as e:
        log.error(f"[{instance_name}] Error scheduling restart: {e}")
