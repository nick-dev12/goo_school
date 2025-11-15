const tabs = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tab-panel");

window.switchTab = function (panelId) {
  tabs.forEach((btn) => {
    if (btn.dataset.tab === panelId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  panels.forEach((panel) => {
    if (panel.id === panelId) {
      panel.classList.add("active");
    } else {
      panel.classList.remove("active");
    }
  });
};

window.showClasse = function (classeId, tabId) {
  const panel = document.getElementById(tabId);
  if (!panel) return;

  panel.querySelectorAll(".classe-tab-btn").forEach((btn) => {
    if (btn.dataset.classe === classeId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  panel.querySelectorAll(".classe-content").forEach((content) => {
    if (content.id === classeId) {
      content.classList.add("active");
    } else {
      content.classList.remove("active");
    }
  });
};

const modalOverlay = document.getElementById("justificationModal");
const closeModalBtn = document.getElementById("closeJustificationModal");
const cancelModalBtn = document.getElementById("cancelJustification");
const noteSelect = document.getElementById("noteSelect");
const nouvelleNoteInput = document.getElementById("nouvelleNoteInput");
const baremeHint = document.getElementById("baremeHint");

const notesDataElement = document.getElementById("notes-data");
let notesData = {};

if (notesDataElement && notesDataElement.textContent.trim()) {
  try {
    notesData = JSON.parse(notesDataElement.textContent);
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn("Impossible d'interpréter les données des notes.", error);
  }
}

const openModal = () => {
  modalOverlay.classList.add("active");
  modalOverlay.setAttribute("aria-hidden", "false");
};

const closeModal = () => {
  modalOverlay.classList.remove("active");
  modalOverlay.setAttribute("aria-hidden", "true");
  noteSelect.innerHTML = "";
  nouvelleNoteInput.value = "";
  nouvelleNoteInput.removeAttribute("max");
  noteSelect.removeAttribute("disabled");
  nouvelleNoteInput.removeAttribute("disabled");
  baremeHint.textContent = "Barème maximum : -";
};

const updateBaremeHint = () => {
  const selectedOption = noteSelect.options[noteSelect.selectedIndex];
  if (!selectedOption) {
    nouvelleNoteInput.removeAttribute("max");
    baremeHint.textContent = "Barème maximum : -";
    return;
  }
  const bareme = selectedOption.dataset.bareme;
  if (bareme) {
    nouvelleNoteInput.setAttribute("max", bareme);
    baremeHint.textContent = `Barème maximum : ${bareme}`;
  } else {
    nouvelleNoteInput.removeAttribute("max");
    baremeHint.textContent = "Barème maximum : -";
  }
};

const justificationButtons = document.querySelectorAll("[data-justify-btn]");

justificationButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const eleveId = button.dataset.eleveId;
    const classeId = button.dataset.classeId || "";
    const matiereId = button.dataset.matiereId || "";
    const eleveNotes = (notesData[eleveId] || []).filter(
      (item) =>
        item.classe_id === classeId &&
        (matiereId === "" || item.matiere_id === matiereId)
    );

    noteSelect.innerHTML = "";

    if (eleveNotes.length === 0) {
      const option = document.createElement("option");
      option.textContent = "Aucune note disponible";
      option.value = "";
      noteSelect.appendChild(option);
      noteSelect.setAttribute("disabled", "disabled");
      nouvelleNoteInput.setAttribute("disabled", "disabled");
      baremeHint.textContent = "Aucune note disponible pour justification.";
      openModal();
      return;
    }

    noteSelect.removeAttribute("disabled");
    nouvelleNoteInput.removeAttribute("disabled");

    eleveNotes.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.label;
      option.dataset.bareme = item.bareme;
      noteSelect.appendChild(option);
    });

    updateBaremeHint();
    openModal();
  });
});

noteSelect.addEventListener("change", updateBaremeHint);
closeModalBtn.addEventListener("click", closeModal);
cancelModalBtn.addEventListener("click", closeModal);

modalOverlay.addEventListener("click", (event) => {
  if (event.target === modalOverlay) {
    closeModal();
  }
});

