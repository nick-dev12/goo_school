document.addEventListener("DOMContentLoaded", () => {
  const openButton = document.getElementById("openPhotoModal");
  const overlay = document.getElementById("photoModalOverlay");
  const closeButton = document.getElementById("closePhotoModal");
  const cancelButton = document.getElementById("cancelPhotoModal");
  const fileInput = document.getElementById("id_photo_profil");
  const previewImage = document.getElementById("photoPreviewImage");
  const previewPlaceholder = document.getElementById("photoPreviewPlaceholder");
  const fileTriggerButton = document.getElementById("fileTriggerButton");
  const carteButton = document.getElementById("openCarteIdentite");
  const carteOverlay = document.getElementById("carteIdentiteOverlay");
  const closeCarteButton = document.getElementById("closeCarteIdentite");
  const printCarteButton = document.getElementById("printCarteProfil");

  if (!openButton || !overlay) {
    return;
  }

  if (overlay.classList.contains("active")) {
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  const toggleModal = (open) => {
    if (!overlay) {
      return;
    }
    if (open) {
      overlay.classList.add("active");
      overlay.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    } else {
      overlay.classList.remove("active");
      overlay.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }
  };

  openButton.addEventListener("click", () => toggleModal(true));

  [closeButton, cancelButton].forEach((button) => {
    if (button) {
      button.addEventListener("click", () => toggleModal(false));
    }
  });

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      toggleModal(false);
    }
  });

  if (fileTriggerButton && fileInput) {
    const focusInput = () => fileInput.click();
    fileTriggerButton.addEventListener("click", (event) => {
      event.preventDefault();
      focusInput();
    });

    fileTriggerButton.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusInput();
      }
    });
  }

  if (fileInput && previewImage && previewPlaceholder) {
    fileInput.addEventListener("change", () => {
      const [file] = fileInput.files || [];
      if (!file) {
        previewImage.classList.remove("visible");
        previewPlaceholder.classList.remove("hidden");
        previewImage.removeAttribute("src");
        return;
      }

      const reader = new FileReader();
      reader.onload = (loadEvent) => {
        previewImage.src = loadEvent.target.result;
        previewImage.classList.add("visible");
        previewPlaceholder.classList.add("hidden");
      };
      reader.readAsDataURL(file);
    });
  }

  const toggleCarte = (open) => {
    if (!carteOverlay) {
      return;
    }
    if (open) {
      carteOverlay.classList.add("active");
      carteOverlay.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    } else {
      carteOverlay.classList.remove("active");
      carteOverlay.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }
  };

  if (carteButton && carteOverlay) {
    carteButton.addEventListener("click", () => toggleCarte(true));
  }

  if (closeCarteButton) {
    closeCarteButton.addEventListener("click", () => toggleCarte(false));
  }

  if (carteOverlay) {
    carteOverlay.addEventListener("click", (event) => {
      if (event.target === carteOverlay) {
        toggleCarte(false);
      }
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay.classList.contains("active")) {
      toggleModal(false);
    }
    if (
      event.key === "Escape" &&
      carteOverlay &&
      carteOverlay.classList.contains("active")
    ) {
      toggleCarte(false);
    }
  });

  if (printCarteButton) {
    printCarteButton.addEventListener("click", () => window.print());
  }
});

