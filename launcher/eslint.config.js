/**
 * ESLint flat config for the launcher.
 *
 * Browser globals are enabled because the launcher targets Chromium
 * kiosk. Recommended rules plus stricter style guidance keep the
 * codebase readable; Prettier owns formatting.
 */
import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      eqeqeq: ['error', 'always'],
      'no-var': 'error',
      'prefer-const': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
];
