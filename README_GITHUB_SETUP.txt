# DELIVERY SCANNER - GITHUB READY

## Easiest upload method
1. Extract this ZIP on your PC.
2. Open your GitHub repository.
3. If GitHub web upload does not accept folders, use GitHub Desktop.
4. Clone the repository to the PC.
5. Copy ALL files/folders from this project into the cloned repository.
6. Replace existing files when asked.
7. Commit and Push.

## Important
Do NOT uninstall the Android app or clear its app data yet.
Existing orders are stored locally under localStorage key `delivery_orders`.
They must be migrated before switching fully to the online database.

## GitHub Actions
- Build APK: existing `.github/workflows/build-apk.yml`
- Build Windows: `.github/workflows/build-windows.yml`

The backend is prepared but is NOT deployed yet. It needs a hosted PostgreSQL database and a `DATABASE_URL`.
