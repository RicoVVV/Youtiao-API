import localforage from "localforage";
import type { StateStorage } from "zustand/middleware";

const store = localforage.createInstance({
    name: "hook-router",
    storeName: "keyvaluepairs",
});

export const localForageStorage: StateStorage = {
    getItem: async (name) => (await store.getItem<string>(name)) ?? null,
    setItem: async (name, value) => {
        await store.setItem(name, value);
    },
    removeItem: async (name) => {
        await store.removeItem(name);
    },
};
