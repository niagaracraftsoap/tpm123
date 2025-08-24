# `tpm123`

`tpm123` securely unseals TPM 1.2-sealed secrets at boot and writes them into per-user, tmpfs-based environment files under `/run/<user>/`.

Secrets are managed as sealed blobs stored in `/etc/blobs/`, and are only made available at runtime to the intended user under hardware-bound conditions. No secrets are persisted in plaintext on disk.

## Overview

- Secrets are sealed using a TPM 1.2 device and stored as binary blob files.
- At boot, a systemd unit runs a script to unseal each blob.
- The resulting secrets are written into:
  - `/run/<user>/env` – for systemd `EnvironmentFile=`
  - `/run/<user>/.env` – for shell or development sourcing
- Both files are owned by the user and stored in tmpfs (`/run`), not persisted across reboots.

## Use Cases

`tpm123` is intended for systems where storing secrets on disk (persistently) poses a risk — whether due to security constraints, threat models, or compliance goals, and where TPM 1.2 is available.

Example scenarios:

- Embedded or industrial Linux systems where full disk encryption is overkill, but runtime secrets are still required
- Long-lived servers or appliances with TPM 1.2 hardware and no TPM 2.0 upgrade path
- Air-gapped or offline systems where injecting secrets at runtime is impractical
- Development environments where secrets should exist only in memory and never touch disk
- Use with systemd units that require per-user secrets available early in the boot process

The tool is designed to be minimal, composable, and safe by default — secrets are hardware-bound, never written to disk in plaintext, and discarded at reboot.

## Blob File Format

Blob files must be located in `/etc/blobs/` and named with the following pattern:

```
/etc/blobs/<username>_<envarname>.blob
```

- The `<username>` must correspond to an existing local user.
- The `<envarname>` is converted to uppercase and sanitized into a valid environment variable name.

- Example: `/etc/blobs/alice_my_secret.blob`

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

A sample systemd unit file is included: `tpm123.service`.

It is intended to run early at boot, before user services that may depend on the unsealed secrets.

To install:

1. Copy `tpm123` to `/usr/local/sbin/`
2. Copy `tpm123.service` to `/etc/systemd/system/`
3. Enable the service:

```
#> systemctl enable tpm123.service
#> systemctl start tpm123
```

4. Reboot or run the service to create/unseal blobs that you `touch` under `/etc/blobs/`.

## Security Notes

- All secrets are sealed to the TPM and unsealed only under correct system state (PCR-bound if configured).
- Secrets are never written to disk unencrypted.
- Secrets exist only in `/run`, which is cleared on reboot.
- Output files are `chmod 400` and `chown <user>:<user>` by default.
- Uses the 'well-known' SRK password for `tpm_sealdata`.

## Requirements

- TPM 1.2 hardware
- `tpm_sealdata` and `tpm_unsealdata` (from `tpm-tools` / `trousers`)
- GNU `base64` with `--wrap=0` support
- Bash

## License

MIT
