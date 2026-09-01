---
name: design-system
description: Use when creating or refactoring a product UI system, shared components, themes, tokens, or dashboard styling. Keeps color, typography, spacing, states, and responsive rules coherent without introducing a large component abstraction prematurely.
metadata:
  version: "3.8.0"
---

# Design System

Create the smallest visual source of truth that makes repeated UI decisions consistent. Prefer the project's existing component library and tokens; extend them only when the current system cannot express the required behavior.

## Workflow

1. **Inventory first.** Locate existing CSS variables, theme files, component primitives, typography rules, breakpoints, and brand references. Record what is already authoritative before adding a second source.
2. **Separate token layers.** Keep raw primitives (palette, type sizes, spacing) separate from semantic roles (`surface`, `text`, `border`, `success`, `danger`) and component decisions (`button-primary-bg`, `table-row-hover`). Components should consume semantic or component tokens, not scattered literals.
3. **Define states explicitly.** For each shared interactive component cover default, hover, active, focus-visible, disabled, loading, success, and error where applicable. State meaning must not depend on color alone.
4. **Define themes deliberately.** Add light/dark or brand variants only when the product needs them. Keep contrast, forced colors, reduced motion, and readable disabled states in the token decisions.
5. **Keep the scale small.** Establish one spacing scale, one type scale, a limited radius/elevation vocabulary, and a small semantic color set. Do not add a token for a single one-off value unless it represents a real design rule.
6. **Document usage, not decoration.** For every token or component variant, state its purpose and when not to use it. Use product language and existing component names.
7. **Verify in context.** Check representative dashboard screens in narrow and wide viewports, with long content and all important states. Remove duplicate tokens or abstractions that have no second consumer.

## Defaults

- Semantic names over appearance names: `text-muted`, not `gray-500`.
- One source of truth for each color, type rule, spacing value, and component state.
- Existing primitives before new components.
- No raw hex values in product components when tokens are available.
- No global restyle when a local component variant closes the task.

## Output before coding

Write a compact contract:

- source files that own the tokens;
- tokens or components reused;
- additions and their consumers;
- state and theme behavior;
- one verification surface.

If a token has no current consumer, do not add it yet.
