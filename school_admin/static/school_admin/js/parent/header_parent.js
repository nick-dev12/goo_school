document.addEventListener("DOMContentLoaded", function () {
  const openNavBtn = document.getElementById("openNavMenu");
  const closeNavBtn = document.getElementById("closeNavMenu");
  const navOverlay = document.getElementById("navOverlay");
  const navigationSection = document.getElementById("navigationSection");
  const liaisonTriggers = document.querySelectorAll("[data-open-liaison]");

  if (!navOverlay || !navigationSection || !closeNavBtn) {
    return;
  }

  function openNavigation() {
    navOverlay.classList.add("active");
    navigationSection.classList.add("active");
    document.body.classList.add("parent-nav-open");
    document.dispatchEvent(new CustomEvent("parentNavOpen"));
  }

  function closeNavigation() {
    navigationSection.classList.remove("active");
    navOverlay.classList.remove("active");
    document.body.classList.remove("parent-nav-open");
    document.dispatchEvent(new CustomEvent("parentNavClose"));
  }

  if (openNavBtn) {
    openNavBtn.addEventListener("click", openNavigation);
  }

  closeNavBtn.addEventListener("click", closeNavigation);

  navOverlay.addEventListener("click", (event) => {
    if (event.target === navOverlay) {
      closeNavigation();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigationSection.classList.contains("active")) {
      closeNavigation();
    }
  });

  window.parentNavMenu = {
    open: openNavigation,
    close: closeNavigation,
  };

  liaisonTriggers.forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      if (window.parentNavMenu) {
        window.parentNavMenu.close();
      }
      if (typeof window.openModal === "function") {
        window.openModal();
      } else {
        const fallback = trigger.dataset.fallback;
        if (fallback) {
          window.location.href = fallback;
        }
      }
    });
  });
});

