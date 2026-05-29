import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="page">
      <header className="page-header">
        <h1>Page Not Found</h1>
        <p>The requested route does not exist in this frontend app.</p>
      </header>
      <div className="panel">
        <Link className="secondary-btn inline-link" to="/smart-composer">
          Go to Compose
        </Link>
      </div>
    </section>
  );
}
