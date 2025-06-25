import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config({
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["dist", "node_modules"],
    languageOptions: {
        ecmaVersion: 2020,
    },
    rules: {
        "@typescript-eslint/no-unused-vars": "warn",
        "@typescript-eslint/explicit-function-return-type": "off",
        "@typescript-eslint/no-explicit-any": "warn",
    },
});
