# 素材图库图片分享 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow an authenticated owner to create a permanent public mobile H5 share from ordered images in one second-level image gallery.

**Architecture:** Persist a share header and ordered snapshot rows beside the existing material-library entities. Creation reads each private source object and writes a new immutable MinIO object before committing the share rows. Authenticated APIs create shares; public APIs render the H5 and stream snapshot images. The existing Vue gallery page owns ordered selection and the WeChat/WeCom handoff.

**Tech Stack:** FastAPI, SQLAlchemy/Postgres runtime schema evolution, MinIO, Vue 3, Ant Design Vue, lucide-vue-next, pytest, pnpm.

**Spec:** `docs/vibe/2026-09-08-material-library-sharing.md`

## Global Constraints

- Only images from one owned second-level image gallery may be shared.
- A new random token and immutable snapshots are created for every share.
- Public H5 is title plus selected images only, mobile-first, anonymous, and long-lived.
- Do not hardcode the deployment domain; use browser origin and optional `MATERIAL_LIBRARY_SHARE_PUBLIC_BASE_URL`.
- Preserve the pre-existing seven modified source files and do not commit or push.

---

### Task 1: Persistence and share creation service

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_content.py`
- Modify: `backend/package/yuxi/storage/postgres/manager.py`
- Modify: `backend/package/yuxi/repositories/material_library_repository.py`
- Modify: `backend/package/yuxi/services/material_library_service.py`
- Test: `backend/test/unit/services/test_material_library_service.py`

**Interfaces:**
- Produces `MaterialShareCreate(item_ids: list[str])` and `create_material_share(db, user, payload)`.
- Produces public share lookup returning title and ordered snapshot objects.

- [ ] Write unit tests for an empty list, a non-child gallery, mixed-gallery selection, ownership rejection, ordered snapshots, and distinct tokens.
- [ ] Run the focused tests and verify they fail because the share creation API does not exist.
- [ ] Add share and share-item models plus idempotent runtime schema statements.
- [ ] Add repository queries and the smallest service that validates items, copies private objects to share paths, persists title/order/token, and cleans copied objects after a database failure.
- [ ] Re-run focused unit tests and verify they pass.

### Task 2: Authenticated and public HTTP boundary

**Files:**
- Modify: `backend/server/routers/material_library_router.py`
- Modify: `backend/package/yuxi/services/material_library_service.py`
- Test: `backend/test/integration/api/test_material_library_router.py`

**Interfaces:**
- `POST /api/material-library/shares` accepts ordered `item_ids` for the current user.
- `GET /api/material-library/shares/{token}/page` is anonymous HTML.
- `GET /api/material-library/shares/{token}/images/{position}` is anonymous image data.

- [ ] Write the integration flow: create a child gallery, upload two images, create a share in supplied order, delete the private source image, then fetch the public H5 and both public snapshot images without credentials.
- [ ] Run the test and verify it fails because the share routes are absent.
- [ ] Implement thin routes delegating to the service, public H5 meta tags, and image responses with safe cache headers.
- [ ] Extend fixture cleanup to remove share rows before users and categories.
- [ ] Re-run the integration flow and verify it passes.

### Task 3: Gallery selection and handoff UI

**Files:**
- Modify: `web/src/apis/material_library_api.js`
- Modify: `web/src/views/MaterialLibraryView.vue`

**Interfaces:**
- `materialLibraryApi.createShare(itemIds)` returns the token and public page path.
- The image-gallery page tracks item IDs in click order and enables sharing only for a second-level gallery.

- [ ] Add the API call.
- [ ] Add selection badges, clear selection on gallery/page changes, and a disabled share button adjacent to upload.
- [ ] Add the two-target modal; on confirmation create the share, copy the browser-origin public URL, attempt `weixin://` or `wxwork://`, and clearly state that the link has been copied for manual send.
- [ ] Run targeted ESLint and production build.

### Task 4: Regression verification

**Files:**
- Modify: `docs/develop-guides/changelog.md`

- [ ] Add one concise user-visible changelog entry.
- [ ] Run focused unit tests, share integration tests, existing material-library unit tests, Python Ruff, frontend lint, frontend production build, and `git diff --check`.
- [ ] Inspect the live Docker page: create a share, load its public H5 while logged out, and confirm source-image deletion does not break the H5 snapshot.
