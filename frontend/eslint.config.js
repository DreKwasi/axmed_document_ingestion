import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";
import vueParser from "vue-eslint-parser";

export default [
  ...pluginVue.configs["flat/recommended"],
  ...tseslint.configs.recommended,
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser
      }
    },
    rules: {
      "vue/html-self-closing": "off",
      "vue/max-attributes-per-line": "off",
      "vue/multi-word-component-names": "off",
      "vue/require-default-prop": "off",
      "vue/singleline-html-element-content-newline": "off"
    }
  },
  {
    ignores: ["dist", "coverage"]
  }
];
