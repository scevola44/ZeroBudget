import { Link } from "react-router-dom";

export function BrandHeader({ className = "" }: { className?: string } = {}) {
  return (
    <Link
      to="/budget"
      className={`flex items-center gap-3 hover:opacity-75 transition-opacity ${className}`}
      aria-label="Go to budget"
    >
      <img src="/favicon.png" alt="" className="w-6 h-6" />
      <span className="text-lg">ZeroBudget</span>
    </Link>
  );
}
