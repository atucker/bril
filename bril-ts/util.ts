import {spawn} from "child_process";
import {Readable} from "stream";

/**
 * Read a readable stream
 */
function readStream(stream: Readable): Promise<string> {
  return new Promise((resolve, reject) => {
    let chunks: string[] = [];
    stream.on("data", function (chunk: string) {
      chunks.push(chunk);
    }).on("end", function () {
      resolve(chunks.join(""))
    }).setEncoding("utf8");
  });
}

/**
 * Read all the data from stdin as a string.
 */
export function readStdin(): Promise<string> {
  return readStream(process.stdin);
}

/**
 * A function to call python code
 */
export async function callPython(prog: string, inpt: string, args?: Array<string>): Promise<any> {
  let spawn_args: Array<string> = [prog];
  if (args) {
    spawn_args = spawn_args.concat(args);
  }
  console.log(`Running ${prog}, sending ${inpt} with args ${spawn_args}`);
  let python = spawn('python', spawn_args);

  python.stdin.write(inpt);
  python.stdin.end();

  return JSON.parse(await readStream(python.stdout));
}

export function unreachable(x: never) {
  throw "impossible case reached";
}