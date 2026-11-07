// A fake /ng/models route (ng/nodes/context_routes.py) over js/ng/models.json: files per purpose, Automatic by the patterns.
import { readFileSync } from "node:fs";

export const TABLE = JSON.parse(readFileSync(new URL("../../../js/ng/models.json", import.meta.url), "utf8"));

export function modelsApi(files = {}) {
  return { apiURL: (path) => path, fetchApi: async (url) => {
    const purposes = new URL(url, "http://comfy").searchParams.get("purposes").split(",").filter((p) => TABLE[p]);
    return { json: async () => Object.fromEntries(purposes.map((p) => {
      const list = files[p] || [];
      const auto = TABLE[p].patterns.map((r) => list.find((n) => new RegExp(r, "i").test(n))).find(Boolean) ?? null;
      return [p, { ...TABLE[p], files: list, auto }];
    })) };
  } };
}
