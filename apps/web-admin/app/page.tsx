import Link from "next/link";

export default function Page() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-2 p-8">
      <h1 className="text-3xl font-extrabold">Agri Admin</h1>
      <p className="text-sm">
        @agri/web-admin · port 3004 · data-theme=&quot;theme-agri&quot;
      </p>
      <p className="text-sm">
        <Link href="/users" className="text-brand underline">
          Users
        </Link>
      </p>
      <p className="text-sm">
        <Link href="/coins" className="text-brand underline">
          Coins
        </Link>
      </p>
      <p className="text-sm">
        <Link href="/ops" className="text-brand underline">
          Ops Console
        </Link>
      </p>
    </main>
  );
}
