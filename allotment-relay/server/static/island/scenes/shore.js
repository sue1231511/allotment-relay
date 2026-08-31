import { renderPlace } from "./place.js?v=island-fix1";

export function renderShore(root) {
  renderPlace(root, { id: "shore", title: "海边" });
}
