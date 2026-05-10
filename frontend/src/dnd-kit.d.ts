// @dnd-kit/accessibility v3.1.1 exposes `scopeLabel` which @dnd-kit/core
// references in its type declarations. Under moduleResolution:"bundler" this
// name isn't automatically placed in scope for user code, so we declare it
// here to satisfy the TypeScript compiler.
declare function scopeLabel(label?: string): string;
