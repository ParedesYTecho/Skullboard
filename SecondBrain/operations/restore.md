# Operation: Restoration & Backup (SecondBrain)

## Procedure
1. SecondBrain markdown files are version-controlled via git.
2. To restore previous state, use standard git checkout:
   ```bash
   git checkout HEAD -- SecondBrain/
   ```
3. To export a clean bundle snapshot, run:
   ```bash
   tar -czf SecondBrain/exports/backup_$(date +%Y%m%d).tar.gz SecondBrain/wiki SecondBrain/catalog SecondBrain/config
   ```
