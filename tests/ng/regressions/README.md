# Open Studio regressions

Created 2026-10-04 against `39e555e`. Repair criteria and evidence:
`D:\comfyui\ComfyUI-Easy-Install\_notes\NG\bug-archiv\BUG-REGRESSIONEN-2026-10-04.md`
(current list: `D:\comfyui\ComfyUI-Easy-Install\_notes\NG\BUG-LISTE.md`).

Run from the repository root:

```powershell
node --test tests/ng/regressions/timeline_boundaries.test.mjs tests/ng/regressions/ai_snapshot.test.mjs tests/ng/regressions/studio_actions.test.mjs tests/ng/regressions/review_state_pending.test.mjs
& 'D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe' tests/ng/regressions/audio_source_window.py
```

The first three JS suites and `audio_source_window.py` passed on `265f045`.
`review_state_pending.test.mjs` passed after the fix in `ab5ab44`; its filename
retains the audit history. All four JS suites (30 cases) and the seven Python cases
now run with `tests/ng/run_tests.py` through `test_verified_regressions.py`.
Do not replace failing assertions with skips or expectations for broken behavior.
`studio_fixture.mjs` reuses the existing minimal DOM and mocks only the ComfyUI API.
No server, network, installed model or GPU is needed.

After further repairs, run their focused tests and the NG suite, then add the newly
verified suites to the normal runner so the regressions remain covered.

The findings BUG-020/021/022 were repaired in commit `7b21c93` and their tests in
`audio_references_pending.py` now all pass. BUG-024 was repaired in `226f53c`.
BUG-025 and BUG-026 were repaired in `ce10f54`.
BUG-027 was repaired in `35d6635` (trimmed `ng_ai_panel.js` to 498 lines).
BUG-028 was repaired in `e8ecde9`.

Open regressions:
- `tests/ng/regressions/lane_removal.test.mjs` (BUG-023: removing an audio lane must remove its clips from the document)
- `tests/ng/test_preset_identity.py` (BUG-018: saving a card without ID must not invent one on load)
- `tests/ng/test_voice_slot_choice.py` (BUG-019: voice named only in shot must reach slot or be reported)
- `tests/ng/regressions/context_card_robustness.test.mjs` (BUG-029: `wirePlayback` sets `audio.volume` to NaN; BUG-030: `selectedRoles`/`contextOptions` throw SyntaxError on non-JSON)
- `tests/ng/regressions/text_card_rename_sync.test.mjs` (BUG-031: text card renameReferences misses first rename; note/ai properties desync)
- `tests/ng/test_media_labels_crash.py` (BUG-032: missing or empty video ctx_id causes AttributeError in `media_labels` / `prompt_labels`)

Run the open regressions:
```powershell
node --test tests/ng/regressions/lane_removal.test.mjs tests/ng/regressions/context_card_robustness.test.mjs tests/ng/regressions/text_card_rename_sync.test.mjs
& 'D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe' tests/ng/test_preset_identity.py
& 'D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe' tests/ng/test_voice_slot_choice.py
& 'D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe' tests/ng/test_media_labels_crash.py
```



