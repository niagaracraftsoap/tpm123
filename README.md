# tpm123

`tpm123` securely unseals TPM 1.2-sealed secrets at boot and writes them into per-user, tmpfs-based environment files under `/run/<user>/`.

Secrets are managed as sealed blobs stored in `/etc/blobs/`, and are only made available at runtime to the intended user under hardware-bound conditions. No secrets are persisted in plaintext on disk.

## Overview

- Secrets are sealed using a TPM 1.2 device and stored as binary blob files.
- At boot, a systemd unit runs a script to unseal each blob.
- The resulting secrets are written into:
  - `/run/<user>/env` – for systemd `EnvironmentFile=`
  - `/run/<user>/.env` – for shell or development sourcing
- Both files are owned by the user and stored in tmpfs (`/run`), not persisted across reboots.

## Blob File Format

Blob files must be located in `/etc/blobs/` and named with the following pattern:

```
/etc/blobs/<username>_<envarname>.blob
```

- Example: `/etc/blobs/alice_APP_SECRET.blob`
- The `<username>` must correspond to an existing local user.
- The `<envarname>` is converted to uppercase and sanitized into a valid environment variable name.

## Behavior

- If a blob file exists but is empty, a new random secret (256 bytes) is generated, sealed to the TPM, and written to the file.
- If a blob file already contains a sealed value, it is unsealed.
- The unsealed secret is written to both `/run/<user>/env` and `/run/<user>/.env` in the following formats:

```sh
# /run/<user>/env
MY_SECRET='base64encodedvalue'

# /run/<user>/.env
export MY_SECRET='base64encodedvalue'
```

## Systemd Integration

A sample systemd unit file is included: `tpm123-unseal.service`.

It is intended to run early at boot, before user services that may depend on the unsealed secrets.

To install:

1. Copy `unseal-blobs.sh` to `/usr/local/sbin/`
2. Copy `tpm123-unseal.service` to `/etc/systemd/system/`
3. Enable the service:

```sh
sudo systemctl daemon-reexec
sudo systemctl enable tpm123-unseal.service
```

4. Reboot to test.

## Security Notes

- All secrets are sealed to the TPM and unsealed only under correct system state (PCR-bound if configured).
- Secrets are never written to disk unencrypted.
- Secrets exist only in `/run`, which is cleared on reboot.
- Output files are `chmod 400` and `chown <user>:<user>` by default.

## Requirements

- TPM 1.2 hardware
- `tpm_sealdata` and `tpm_unsealdata` (from `tpm-tools` / trousers)
- GNU `base64` with `--wrap=0` support
- Bash

## License

MIT

---

For more information, see the source script or open an issue.
