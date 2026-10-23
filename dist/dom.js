// Small DOM helpers shared by the view controllers.
export const $ = id => document.getElementById(id);

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export const pct = n => (n * 100).toFixed(n >= 0.1 ? 0 : 1) + '%';
