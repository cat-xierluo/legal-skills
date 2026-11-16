/* Optional page-local cue control. The host owns activation and navigation. */
(() => {
  "use strict";

  function mount(root) {
    const choices = [...root.querySelectorAll("[data-step-to]")];
    const moves = [...root.querySelectorAll("[data-step-by]")];
    const notes = [...root.querySelectorAll("[data-step-note]")];
    const last = choices.length - 1;
    if (last < 1 || choices.some((button, i) => button.dataset.stepTo !== String(i))) {
      throw new Error("A slide scene needs consecutive step buttons starting at 0");
    }

    let current = -1;
    function go(index) {
      if (!Number.isInteger(index) || index < 0 || index > last || index === current) return false;
      current = index;
      root.dataset.step = String(index);
      choices.forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
      moves.forEach(button => {
        const target = index + Number(button.dataset.stepBy);
        if (target < 0 || target > last) button.setAttribute("aria-disabled", "true");
        else button.removeAttribute("aria-disabled");
      });
      notes.forEach(note => { note.hidden = Number(note.dataset.stepNote) !== index; });
      root.dispatchEvent(new CustomEvent("slides:step", { detail: { index } }));
      return true;
    }

    root.addEventListener("click", event => {
      const button = event.target.closest("button[data-step-to],button[data-step-by]");
      if (!button || !root.contains(button)) return;
      if (button.hasAttribute("data-step-to")) go(Number(button.dataset.stepTo));
      else go(current + Number(button.dataset.stepBy));
    });

    go(0);
    return Object.freeze({
      go,
      get index() { return current; },
      get last() { return last; },
      handleKey(event) {
        if (event.defaultPrevented || event.key !== " " || event.ctrlKey || event.metaKey || event.altKey ||
            event.target?.closest?.("button,a,input,select,textarea,[contenteditable],[role=button]")) return false;
        if (!event.repeat && !event.shiftKey && current === last) return false;
        event.preventDefault();
        if (!event.repeat) go(current + (event.shiftKey ? -1 : 1));
        return true;
      },
    });
  }

  window.SlidesSteps = Object.freeze({ mount });
})();
