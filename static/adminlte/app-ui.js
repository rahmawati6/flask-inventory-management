(function () {
    "use strict";

    function ensureToastContainer() {
        let container = document.querySelector(".app-toast-container");
        if (!container) {
            container = document.createElement("div");
            container.className = "app-toast-container";
            document.body.appendChild(container);
        }
        return container;
    }

    function showToast(message, type) {
        const container = ensureToastContainer();
        const toast = document.createElement("div");
        toast.className = "app-toast app-toast-" + (type || "info");
        toast.innerHTML = '<span>' + message + '</span><button type="button" aria-label="Tutup">&times;</button>';
        container.appendChild(toast);

        const close = function () {
            toast.classList.add("is-hiding");
            setTimeout(function () {
                toast.remove();
            }, 220);
        };

        toast.querySelector("button").addEventListener("click", close);
        setTimeout(close, 4200);
    }

    function ensureConfirmDialog() {
        let dialog = document.querySelector(".app-confirm-backdrop");
        if (dialog) return dialog;

        dialog = document.createElement("div");
        dialog.className = "app-confirm-backdrop";
        dialog.innerHTML = [
            '<div class="app-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="appConfirmTitle">',
            '<div class="app-confirm-icon"><i class="fas fa-exclamation-triangle"></i></div>',
            '<h3 id="appConfirmTitle">Konfirmasi Tindakan</h3>',
            '<p id="appConfirmMessage">Apakah Anda yakin?</p>',
            '<div class="app-confirm-actions">',
            '<button type="button" class="btn btn-secondary" data-confirm-cancel>Batal</button>',
            '<button type="button" class="btn btn-danger" data-confirm-ok>Ya, lanjutkan</button>',
            '</div>',
            '</div>'
        ].join("");
        document.body.appendChild(dialog);
        return dialog;
    }

    function confirmAction(message, onConfirm) {
        const dialog = ensureConfirmDialog();
        dialog.querySelector("#appConfirmMessage").textContent = message || "Apakah Anda yakin?";
        dialog.classList.add("is-visible");

        const ok = dialog.querySelector("[data-confirm-ok]");
        const cancel = dialog.querySelector("[data-confirm-cancel]");

        const cleanup = function () {
            dialog.classList.remove("is-visible");
            ok.replaceWith(ok.cloneNode(true));
            cancel.replaceWith(cancel.cloneNode(true));
        };

        dialog.querySelector("[data-confirm-cancel]").addEventListener("click", cleanup);
        dialog.querySelector("[data-confirm-ok]").addEventListener("click", function () {
            cleanup();
            onConfirm();
        });
    }

    function enhanceFlashMessages() {
        document.querySelectorAll(".alert").forEach(function (alert) {
            const message = alert.textContent.replace("×", "").trim();
            if (!message) return;

            let type = "info";
            if (alert.classList.contains("alert-success")) type = "success";
            if (alert.classList.contains("alert-danger")) type = "danger";
            if (alert.classList.contains("alert-warning")) type = "warning";

            showToast(message, type);
            alert.classList.add("app-alert-inline");
        });
    }

    function enhanceConfirmButtons() {
        document.addEventListener("click", function (event) {
            const trigger = event.target.closest("[data-confirm]");
            if (!trigger || trigger.dataset.confirmed === "true") return;

            event.preventDefault();
            confirmAction(trigger.dataset.confirm, function () {
                if (trigger.tagName === "A") {
                    window.location.href = trigger.href;
                    return;
                }

                if (trigger.matches("button[type='submit']")) {
                    trigger.dataset.confirmed = "true";
                    trigger.click();
                    setTimeout(function () {
                        delete trigger.dataset.confirmed;
                    }, 1000);
                }
            });
        });
    }

    function enhanceForms() {
        document.querySelectorAll("form").forEach(function (form) {
            form.addEventListener("submit", function () {
                const button = form.querySelector("button[type='submit']:focus") || form.querySelector("button[type='submit']");
                if (!button || button.dataset.loadingApplied === "true") return;
                button.dataset.loadingApplied = "true";
                button.dataset.originalText = button.innerHTML;
                button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Memproses...';
                button.disabled = true;
            });
        });
    }

    function enhanceTables() {
        document.querySelectorAll(".table-card").forEach(function (card) {
            const table = card.querySelector("table");
            if (!table || card.querySelector(".table-tools")) return;

            const responsive = card.querySelector(".table-responsive");
            if (!responsive) return;

            const rows = Array.from(table.querySelectorAll("tbody tr"));
            const realRows = rows.filter(function (row) {
                return row.querySelectorAll("td").length > 1;
            });

            const tools = document.createElement("div");
            tools.className = "table-tools";
            tools.innerHTML = [
                '<div class="table-count"><i class="fas fa-list-ul"></i> <span>' + realRows.length + '</span> data</div>',
                '<label class="table-search"><i class="fas fa-search"></i><input type="search" placeholder="Cari data..."></label>'
            ].join("");
            responsive.parentNode.insertBefore(tools, responsive);

            const input = tools.querySelector("input");
            input.addEventListener("input", function () {
                const keyword = input.value.trim().toLowerCase();
                let visible = 0;

                realRows.forEach(function (row) {
                    const match = row.textContent.toLowerCase().includes(keyword);
                    row.style.display = match ? "" : "none";
                    if (match) visible += 1;
                });

                tools.querySelector(".table-count span").textContent = visible;
            });
        });
    }

    function enhanceTooltips() {
        document.querySelectorAll(".action-btn, .btn-sm").forEach(function (button) {
            if (button.getAttribute("title")) return;
            const text = button.textContent.trim();
            if (text) button.setAttribute("title", text);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        enhanceFlashMessages();
        enhanceConfirmButtons();
        enhanceForms();
        enhanceTables();
        enhanceTooltips();
    });

    window.AppUI = {
        showToast: showToast,
        confirmAction: confirmAction
    };
})();
