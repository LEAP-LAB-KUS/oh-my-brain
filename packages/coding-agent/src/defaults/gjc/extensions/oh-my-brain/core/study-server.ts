/**
 * Local study server (port of harness/study_server.py): serves learning/
 * pages and records browser quiz outcomes.
 *
 *   GET  /...      -> files under learning/ (dashboard, materials)
 *   POST /record   -> {"kc_hint": str, "question": str, "correct": 0|1}
 *                     recorded to the SQLite learner record, exactly like
 *                     agent-graded outcomes
 *
 * Everything stays on localhost; no external requests.
 */
import * as fs from "node:fs";
import * as http from "node:http";
import * as path from "node:path";
import type { OmbDb } from "./db";
import type { OmbPaths } from "./paths";

export const STUDY_SERVER_PORT = 8787;

const MIME: Record<string, string> = {
	".html": "text/html; charset=utf-8",
	".css": "text/css; charset=utf-8",
	".js": "text/javascript; charset=utf-8",
	".json": "application/json",
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".svg": "image/svg+xml",
	".mp4": "video/mp4",
	".webm": "video/webm",
};

export interface StudyServerHandle {
	port: number;
	close(): void;
}

function readBody(req: http.IncomingMessage): Promise<string> {
	return new Promise((resolve, reject) => {
		const chunks: Buffer[] = [];
		req.on("data", c => chunks.push(c));
		req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
		req.on("error", reject);
	});
}

export function startStudyServer(
	paths: OmbPaths,
	db: OmbDb,
	options?: { port?: number; onRecord?: () => void },
): Promise<StudyServerHandle> {
	const port = options?.port ?? STUDY_SERVER_PORT;
	const server = http.createServer(async (req, res) => {
		try {
			const url = new URL(req.url ?? "/", "http://127.0.0.1");
			if (req.method === "GET" && url.pathname === "/omb-health") {
				res.writeHead(200, { "Content-Type": "application/json" }).end(
					JSON.stringify({ omb: true, root: paths.root }),
				);
				return;
			}
			if (req.method === "POST") {
				if (url.pathname.replace(/\/+$/, "") !== "/record") {
					res.writeHead(404).end();
					return;
				}
				const data = JSON.parse(await readBody(req));
				const q = db.assign(String(data.question), String(data.kc_hint));
				db.recordOutcome("local", q, Number(data.correct));
				options?.onRecord?.();
				const body = JSON.stringify({ ok: true, kc_id: q.kcId, q_id: q.qId });
				res.writeHead(200, { "Content-Type": "application/json" }).end(body);
				return;
			}
			// static files under learning/
			let filePath = path.normalize(path.join(paths.learningDir, decodeURIComponent(url.pathname)));
			if (!filePath.startsWith(paths.learningDir)) {
				res.writeHead(403).end();
				return;
			}
			if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
				filePath = path.join(filePath, "dashboard.html");
			}
			if (!fs.existsSync(filePath)) {
				res.writeHead(404).end("not found");
				return;
			}
			const mime = MIME[path.extname(filePath).toLowerCase()] ?? "application/octet-stream";
			res.writeHead(200, { "Content-Type": mime }).end(fs.readFileSync(filePath));
		} catch (err) {
			res.writeHead(400).end(String(err));
		}
	});
	return new Promise((resolve, reject) => {
		server.once("error", reject);
		server.listen(port, "127.0.0.1", () => {
			const address = server.address();
			const boundPort = typeof address === "object" && address ? address.port : port;
			resolve({
				port: boundPort,
				close: () => server.close(),
			});
		});
	});
}

/** True when an oh-my-brain study server for THIS project answers on `port`. */
export async function probeStudyServer(root: string, port: number, timeoutMs = 400): Promise<boolean> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const res = await fetch(`http://127.0.0.1:${port}/omb-health`, { signal: controller.signal });
		if (!res.ok) return false;
		const body = (await res.json()) as { omb?: boolean; root?: string };
		return body.omb === true && body.root === root;
	} catch {
		return false;
	} finally {
		clearTimeout(timer);
	}
}
