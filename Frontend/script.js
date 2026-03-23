// Mobile nav toggle
const navToggle = document.getElementById("navToggle");
const navMenu = document.getElementById("navMenu");

if (navToggle && navMenu) {
  navToggle.addEventListener("click", () => {
    const isOpen = navMenu.classList.toggle("show");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });
}

// FAQ accordion
document.querySelectorAll(".faq-q").forEach((btn) => {
  btn.addEventListener("click", () => {
    const expanded = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!expanded));
  });
});

// Footer year
document.getElementById("year").textContent = new Date().getFullYear();

// Demo toast
const toastBtn = document.getElementById("demoToast");
const toast = document.getElementById("toast");

if (toastBtn && toast) {
  toastBtn.addEventListener("click", () => {
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  });
}

const WISHLIST_KEY = "cloudmart_wishlist_demo";

function loadWishlist() {
  try {
    return JSON.parse(localStorage.getItem(WISHLIST_KEY)) || [];
  } catch {
    return [];
  }
}

function saveWishlist(items) {
  localStorage.setItem(WISHLIST_KEY, JSON.stringify(items));
}

function upsertWishlistItem(newItem) {
  const items = loadWishlist();
  const existingIndex = items.findIndex(i => i.id === newItem.id);

  if (existingIndex !== -1) {
    items[existingIndex] = { ...items[existingIndex], ...newItem };
  } else {
    items.push(newItem);
  }

  saveWishlist(items);
  renderWishlist();
}

function removeWishlistItem(id) {
  const items = loadWishlist().filter(i => i.id !== id);
  saveWishlist(items);
  renderWishlist();
}

function renderWishlist() {
  const grid = document.getElementById("wishlistGrid");
  const empty = document.getElementById("wishlistEmpty");

  if (!grid || !empty) return; // prevents errors if section isn't present

  const items = loadWishlist();
  grid.innerHTML = "";

  if (!items.length) {
    empty.style.display = "block";
    return;
  }

  empty.style.display = "none";

  items.forEach(item => {
    const statusLabel = item.status === "sold"
      ? `<p class="muted"><strong>Status:</strong> Sold</p>`
      : `<p class="muted"><strong>Status:</strong> Active</p>`;

    const card = document.createElement("article");
    card.className = "feature-card product-card";
    card.innerHTML = `
      <img src="${item.img}" class="product-img product-img-small" alt="${item.title}">
      <h3>${item.title}</h3>
      <p class="muted">${item.price}</p>
      ${statusLabel}
      <button class="btn btn-outline full" data-remove="${item.id}">Remove</button>
    `;

    grid.appendChild(card);
  });

  grid.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", () => removeWishlistItem(btn.dataset.remove));
  });
}

// Add to Wishlist button handler
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".add-to-wishlist");
  if (!btn) return;

  const item = {
    id: btn.dataset.id,
    title: btn.dataset.title,
    price: btn.dataset.price,
    status: btn.dataset.status || "active",
    img: btn.dataset.img || ""
  };

  upsertWishlistItem(item);
});

// Initial render
document.addEventListener("DOMContentLoaded", renderWishlist);
