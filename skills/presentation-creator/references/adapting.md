# Adapting an Existing Talk



1. Check if the talk has been ingested by the vault. If not, process it first.
2. Read the original talk's analysis from `{vault_root}/analyses/`.
3. Copy the previous deck as the starting point — do NOT start from a fresh
   template.
4. Start at Phase 1 with the original spec pre-filled, modify as needed.
5. Auto-generate an adaptation checklist: footer, shownotes slug, time-sensitive
   content, slide budget, profanity register, locale references, commercial
   intent.
6. For structural deck work after the outline is approved, invoke
   `Skill(skill: "presentation-builder")` with the copied deck and requested edits.
   Keep the existing deck rather than rebuilding from a fresh template.
