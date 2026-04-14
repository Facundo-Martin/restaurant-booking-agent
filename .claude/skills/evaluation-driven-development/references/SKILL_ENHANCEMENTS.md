# SKILL.md Enhancements — RFC 2119 & IF/THEN Clarity

**Date:** 2026-04-08
**Rationale:** Incorporate best practices from Agent-SOP eval workflow while maintaining EDD's architectural guidance strength

---

## Summary of Changes

The updated SKILL.md now uses RFC 2119 constraint language (MUST/SHOULD/MAY) and IF/THEN notation to make phase progression unambiguous and machine-parseable.

### Key Enhancements

1. **Process Overview** — Added RFC 2119 keywords + IF/THEN notation for conditional phases
2. **Step 1 (Clarify Requirements)** — Changed "If YES → ..." to "IF YES THEN: ..." for clarity
3. **Step 3 (Strategy)** — Explicit MUST/SHOULD/MAY per phase with success thresholds (≥80% pass rate)
4. **Phase 2a Acceptance** — Split into MUST-Pass / SHOULD-Pass / MAY-Pass to prevent scope creep
5. **Phase 2b/2c Headers** — Added "IF agent.uses_tools THEN..." and "IF agent.is_multiturn THEN..."
6. **Phase 2d/2e Descriptions** — Changed to "SHOULD DO" with skip conditions
7. **Phase 2f Description** — Changed to "MAY DO" with IF/THEN condition
8. **Best Practices** — Updated all 8 practices with RFC 2119 tags
9. **NEW: RFC 2119 Reference Section** — Explanation table defining constraint language

---

## Impact

- **Clarity**: Readers can scan for RFC 2119 keywords to understand which steps block progression
- **Conditional Logic**: IF/THEN notation explicitly shows when to skip phases (no tools → skip 2b, single-turn → skip 2c)
- **Scope Control**: MUST-Pass vs SHOULD-Pass separation prevents "nice-to-have" features blocking progression
- **Machine-Readability**: RFC 2119 keywords enable constraint parsing by scripts and other tools

---

## What Wasn't Changed

- **Code Examples**: All Python snippets remain unchanged (examples are concrete and correct)
- **Overall Structure**: Three-phase approach (Architecture, Implementation, Validation) maintained
- **Content Volume**: File length roughly the same (enhancements are additive, not duplicative)

---

## Testing Strategy (Next Session)

Focus on:
1. **Phase Progression Logic** — Can readers correctly skip Phase 2b if agent has no tools?
2. **Acceptance Criteria Clarity** — Do MUST/SHOULD/MAY checkboxes feel natural?
3. **RFC 2119 Understanding** — Do readers understand the constraint language after reading the reference table?
4. **IF/THEN Readability** — Is conditional logic clearer with IF/THEN notation?

---

For full comparison with Agent-SOP and Strands Eval SOP, see `ANALYSIS_EDD_VS_AGENTSOP.md`.
