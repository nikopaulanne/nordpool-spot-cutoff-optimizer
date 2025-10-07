# Contributing to Nordpool Spot Cutoff Optimizer

Thank you for your interest in contributing! This project thrives on community input, especially **real-world integration examples**.

## How to Contribute

### 1. Share Your Integration Example

The most valuable contribution is **showing how YOU integrated this with YOUR system**.

**To contribute an example:**

1. Fork this repository
2. Create a folder: `examples/your_system_name/`
3. Include:
   - `README.md` - Describe your setup, equipment, results
   - `configuration.yaml` - Your sensor/input configurations
   - `automations.yaml` - Your automation logic
   - `lovelace.yaml` (optional) - Dashboard example
   - `images/` (optional) - Screenshots of results

4. Submit a Pull Request

**Examples we'd love to see:**
- Different HVAC brands (Mitsubishi, Daikin, etc.)
- Hybrid heating systems (multiple heat sources)
- Water heaters with different control methods
- EV charging integration
- Pool/spa heating
- Industrial equipment
- Multi-load coordination

### 2. Improve Documentation

- Fix typos or unclear explanations
- Add translations
- Create diagrams or illustrations
- Write tutorials

### 3. Enhance Code

- Bug fixes
- Performance improvements
- New features (discuss in Issues first)
- Better error handling

### 4. Report Issues

Found a bug? Have a question? [Open an Issue](../../issues)

**Good bug reports include:**
- Home Assistant version
- Nordpool integration version
- Error logs (remove sensitive data!)
- Steps to reproduce
- Expected vs actual behavior

## Code Style

- Python: Follow PEP 8
- YAML: 2-space indentation
- Comments: Explain WHY, not just WHAT
- Variable names: Clear and descriptive

## Testing

Before submitting:
- Test your changes in a real Home Assistant environment
- Verify no breaking changes to existing functionality
- Document any new parameters or configuration

## Pull Request Process

1. **Fork & Branch**: Create a feature branch from `main`
2. **Commit**: Use clear commit messages
3. **Test**: Verify everything works
4. **Document**: Update README/docs if needed
5. **Submit PR**: Explain what and why
6. **Be patient**: Reviews may take a few days

## Example PR Description Template

```markdown
## Description
[What does this PR do?]

## Motivation
[Why is this change needed?]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Integration example
- [ ] Documentation
- [ ] Other (please describe)

## Testing
[How did you test this?]

## Screenshots (if applicable)
[Add screenshots of results, dashboards, etc.]

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have tested this in a real HA environment
- [ ] I have updated documentation
- [ ] My changes don't break existing functionality
```

## Questions?

Ask in:
- [GitHub Discussions](../../discussions)
- [Home Assistant Community Forum](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for helping make energy optimization accessible to everyone! 🙌**
