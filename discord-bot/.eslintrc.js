module.exports = {
    root: true,
    env: { node: true },
    parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
    },
    extends: ["eslint:recommended", "prettier"],
    rules: {
        "no-prototype-builtins": "off",
    },
};
