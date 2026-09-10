/** @odoo-module **/

const FORM_SELECTOR = ".o_form_view";
const CHATTER_SELECTOR = ".o-mail-Form-chatter, .o_FormRenderer_chatterContainer";
const PREVIEW_SELECTOR = ".o_attachment_preview";
const BUTTON_CLASS = "o_chatter_toggle_btn";
const TOOLBAR_CLASS = "o_chatter_toggle_toolbar";
const CHATTER_HIDDEN_CLASS = "o_chatter_hidden";
const PREVIEW_HIDDEN_CLASS = "o_preview_hidden";
const STORAGE_KEY = "custom_chatter_toggle.state";

// The button cycles through view states, remembered per browser profile:
//   0 = show everything (default layout)
//   1 = hide the attachment (PDF) preview pane — form takes full width
//   2 = hide the preview AND the chatter
// Forms without a preview pane only use states 0 and 2 (a plain chatter
// toggle); a stored state of 1 renders the same as 0 there.

function loadState() {
    try {
        const state = parseInt(window.localStorage.getItem(STORAGE_KEY), 10);
        return [0, 1, 2].includes(state) ? state : 0;
    } catch {
        return 0;
    }
}

function saveState(state) {
    try {
        window.localStorage.setItem(STORAGE_KEY, String(state));
    } catch {
        // Storage disabled (private browsing): state just won't persist.
    }
}

function getPreferredTarget(form) {
    // Anchor the floating button to the form sheet (left pane) so it never
    // overlays the attachment preview / PDF toolbar on the right.
    return (
        form.querySelector(".o_form_sheet_bg") ||
        form.querySelector(".o_content") ||
        form
    );
}

function hasChatter(form) {
    return Boolean(form.querySelector(CHATTER_SELECTOR));
}

function hasPreview(form) {
    return Boolean(form.querySelector(PREVIEW_SELECTOR));
}

function updateButton(button, form, state) {
    let label;
    if (state === 2) {
        label = "Show All";
    } else if (state === 1 || !hasPreview(form)) {
        label = "Hide Chatter";
    } else {
        label = "Show Chatter (hide PDF)";
    }
    button.textContent = state === 2 ? "«" : "»";
    button.setAttribute("aria-pressed", state === 0 ? "false" : "true");
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
}

function applyState(form, state) {
    form.classList.toggle(PREVIEW_HIDDEN_CLASS, state >= 1);
    form.classList.toggle(CHATTER_HIDDEN_CLASS, state === 2);
    const button = form.querySelector(`.${BUTTON_CLASS}`);
    if (button) {
        updateButton(button, form, state);
    }
}

function createButton(form) {
    const wrapper = document.createElement("div");
    wrapper.className = TOOLBAR_CLASS;

    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn btn-light ${BUTTON_CLASS}`;
    button.dataset.chatterToggle = "1";

    updateButton(button, form, loadState());

    wrapper.appendChild(button);
    return wrapper;
}

function ensureButton(form) {
    if (!(form instanceof Element)) {
        return;
    }
    if (!hasChatter(form)) {
        return;
    }
    if (form.querySelector(`.${BUTTON_CLASS}`)) {
        return;
    }

    const target = getPreferredTarget(form);
    if (!target) {
        return;
    }

    const buttonWrapper = createButton(form);
    target.appendChild(buttonWrapper);
    applyState(form, loadState());
}

function scanForms(root = document) {
    root.querySelectorAll(FORM_SELECTOR).forEach((form) => {
        ensureButton(form);
    });
}

function handleClick(ev) {
    const button = ev.target.closest(`.${BUTTON_CLASS}`);
    if (!button) {
        return;
    }

    const form = button.closest(FORM_SELECTOR);
    if (!form) {
        return;
    }

    let state = loadState();
    if (hasPreview(form)) {
        state = (state + 1) % 3;
    } else {
        // No preview pane: skip state 1, plain show/hide chatter.
        state = state === 2 ? 0 : 2;
    }
    saveState(state);
    applyState(form, state);
}

function start() {
    document.addEventListener("click", handleClick);

    scanForms();

    const root = document.documentElement;
    if (!(root instanceof Node)) {
        return;
    }

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (!(node instanceof Element)) {
                    continue;
                }
                if (node.matches?.(FORM_SELECTOR)) {
                    ensureButton(node);
                } else {
                    scanForms(node);
                }
                // The chatter and the attachment preview mount after the
                // form (and the preview only on records that have a file),
                // so re-apply the remembered state whenever something new
                // lands inside a form view.
                const form = node.closest?.(FORM_SELECTOR);
                if (form) {
                    applyState(form, loadState());
                }
            }
        }
    });

    observer.observe(root, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
