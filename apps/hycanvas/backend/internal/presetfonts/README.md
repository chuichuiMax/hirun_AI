# Xiaohongshu preset fonts

This directory contains the 25 unique TTF/OTF binaries selected from the
user-provided font package. Each filename is the lowercase SHA-256 digest of
the exact file bytes, followed by its original container extension. Duplicate
source files are intentionally represented once.

The repository owner confirmed that these font binaries may be publicly
redistributed with the repository and its HyCanvas images. Keep this
authorization note with the resources when mirroring or packaging them.

The files are Git LFS objects. Production builds use `-tags embed`; development
builds read this directory from the bind-mounted source tree.
