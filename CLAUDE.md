- Always run with `uv`

# MCPcat Package Publishing Info

## Package Details
- Package name: `mcpcat`
- Current version: `0.1.0b1` (pre-alpha)
- PyPI URL: https://pypi.org/project/mcpcat/
- Author: MCPCat
- Email: support@mcpcat.io
- License: MIT
- GitHub: https://github.com/MCPCat/mcpcat-python-sdk

## Publishing Commands
```bash
# Build the package
uv build

# Publish to PyPI
export UV_PUBLISH_TOKEN="your-pypi-token"
uv publish
```

## Version Conventions
- Using beta versions (e.g., 0.1.0b1, 0.1.0b2) for pre-release
- TypeScript SDK uses: 0.1.0-beta.1 format
- Python uses: 0.1.0b1 format (PEP 440)

## Important Notes
- PyPI packages are immutable - cannot undo publishes
- Must increment version for each new release
- Package supports Python >=3.10