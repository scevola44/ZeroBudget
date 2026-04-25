import { Link } from "react-router-dom";

export function BrandHeader({ className = "" }: { className?: string } = {}) {
  return (
    <Link
      to="/budget"
      className={`flex items-center gap-2 hover:opacity-75 transition-opacity ${className}`}
      aria-label="Go to budget"
    >
      <img src="/favicon.png" alt="" className="w-5 h-5" />
      <span>ZeroBudget</span>
    </Link>
  );
}
