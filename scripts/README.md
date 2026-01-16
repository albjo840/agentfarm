# AgentFarm Scripts

Utility scripts for AgentFarm infrastructure and deployment.

## Scripts

### wireguard-setup.sh

Complete WireGuard VPN setup script with DuckDNS integration. Enables secure remote access to AgentFarm from mobile devices.

**Usage:**

```bash
# Full installation (requires root)
sudo ./wireguard-setup.sh install

# Add new peer (generates QR code)
sudo ./wireguard-setup.sh add-peer <peer-name>

# List all configured peers
sudo ./wireguard-setup.sh list-peers

# Show WireGuard status
sudo ./wireguard-setup.sh status
```

**Features:**
- Automatic WireGuard installation and key generation
- DuckDNS dynamic DNS integration
- QR code generation for easy mobile setup
- IP forwarding and firewall configuration
- Systemd service setup for persistence

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `DUCKDNS_DOMAIN` | `taborsen.duckdns.org` | DuckDNS domain name |
| `DUCKDNS_TOKEN` | (none) | DuckDNS API token |

**Network Configuration:**
- VPN Subnet: `10.0.0.0/24`
- Server IP: `10.0.0.1`
- Port: `51820/UDP`

**After Setup:**
1. Open UDP port 51820 on your router/firewall
2. Configure port forwarding if behind NAT
3. Test connection from mobile device

**See also:** [docs/WIREGUARD_SETUP.md](../docs/WIREGUARD_SETUP.md)

## Adding New Scripts

When adding new scripts:

1. Use bash with `set -e` for error handling
2. Add usage information in script header
3. Use colored output for user feedback
4. Check for root if elevated privileges needed
5. Document in this README

## Troubleshooting

### WireGuard QR-kod skannas inte

**Problem:** "Kan inte importera tunnel: QR-kod hittas inte i bilden"

**Orsak:** Terminal-QR-koden (ANSI-format) skannas inte bra via screenshots.

**Lösning:**

1. **Använd PNG-filen direkt:**
   ```bash
   # Hitta PNG-filen
   sudo ls /etc/wireguard/peers/

   # Kopiera till din home
   sudo cp /etc/wireguard/peers/<peer>/qr.png ~/wireguard-qr.png
   sudo chown $USER ~/wireguard-qr.png

   # Visa bilden (eller överför till telefon)
   xdg-open ~/wireguard-qr.png
   ```

2. **Regenerera QR-koden med bättre kvalitet:**
   ```bash
   # Skapa större QR-kod
   sudo qrencode -s 10 -o ~/wireguard-qr.png < /etc/wireguard/peers/<peer>/<peer>.conf
   ```

3. **Importera config-filen manuellt:**
   - Kopiera `.conf`-filen till telefonen
   - I WireGuard app: (+) → "Import from file"

4. **Kontrollera att qrencode är installerat:**
   ```bash
   which qrencode || sudo apt install qrencode
   ```

## Security Notes

- All scripts should validate inputs
- Avoid storing secrets in scripts (use environment variables)
- VPN scripts require careful key management
- Test in staging before production
