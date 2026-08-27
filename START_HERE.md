# START HERE

If you return to MCP Light Memory after months or years, follow these steps:

1. Install into the target repo (always pass the client — see `INSTALL.md`):

   ```powershell
   python .\install.py "D:\path\to\project" --client warp
   ```

2. Restart Warp/OpenCode (JetBrains: complete the IDE UI step the installer printed).
3. In the repo run:

   ```powershell
   python .agents\skills\internal-rag\mlm.py context --task "current task"
   ```

4. If `RECOVERY REQUIRED` appears, follow `docs/RECOVERY.md`.
5. Before publishing the repo run `python privacy_check.py "D:\path\to\project"`.
6. To fully clean the final project, run `python uninstall.py "D:\path\to\project"`.
7. Run `python .agents\skills\internal-rag\mlm.py doctor` for a health check.

Full documentation: `README.md`, `INSTALL.md` and the `docs/` directory.
