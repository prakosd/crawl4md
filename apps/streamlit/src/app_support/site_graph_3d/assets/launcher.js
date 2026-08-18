// Streamlit CCv2 launcher for the 3D site-graph viewer. Renders a button that
// matches Streamlit's secondary buttons; on click it opens the crawl's published
// static viewer URL (data.url) in a new tab. The click handler runs synchronously
// inside the user gesture, so the tab opens without tripping the popup blocker.
// CCv2 runs in the page context (no iframe), so window/document access here is the
// top document.
const ICON = `
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
  <circle cx="14.5" cy="9" r="5"></circle>
  <circle cx="6.5" cy="15.5" r="3.4"></circle>
  <circle cx="16.5" cy="17.5" r="2.4"></circle>
</svg>`;

const instances = new WeakMap();

export default function (component) {
  const { data, parentElement } = component;

  let instance = instances.get(parentElement);
  if (!instance) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sg-launch-btn";
    button.innerHTML = `${ICON}<span class="sg-launch-label"></span>`;
    instance = { button, data };
    instances.set(parentElement, instance);
    button.addEventListener("click", () => {
      if (instance.data.disabled) return;
      openViewer(instance.data.url);
    });
    parentElement.appendChild(button);
  }

  instance.data = data;
  instance.button.querySelector(".sg-launch-label").textContent =
    data.label || "Explore in 3D";
  instance.button.title = data.help || "";
  instance.button.disabled = Boolean(data.disabled);
  instance.button.setAttribute("aria-disabled", String(Boolean(data.disabled)));
  // Stretch to fill the column (ready-result panel) vs. hug content (tree row).
  const block = Boolean(data.full_width);
  instance.button.classList.toggle("sg-launch-btn--block", block);
  // parentElement is a ShadowRoot (isolate_styles=True default); .host is the actual HTMLElement.
  (parentElement.host ?? parentElement).style.width = block ? "100%" : "";

  return () => {
    parentElement.innerHTML = "";
    instances.delete(parentElement);
  };
}

function openViewer(path) {
  if (!path) return;
  // Resolve against the app's base URL so it also works under a base-path deploy,
  // then open the real static file in a new tab (refreshable, unlike a blob URL).
  const anchor = document.createElement("a");
  anchor.href = new URL(path, document.baseURI).href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
