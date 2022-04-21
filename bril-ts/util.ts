import {spawn} from "child_process";
import {Readable} from "stream";

var path = require('path');
var scriptName = path.basename(__filename);

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
  //console.error(`Running ${prog}, sending ${inpt} with args ${spawn_args}`);
  let python = spawn('python', spawn_args);

  // Let's see those error messages...
  python.stderr.on('data', (data) => {
    console.error(`Python: ${data}`);
  });

  console.error(`Writing: ${python.stdin.write(inpt)}`);
  console.error(`Ending: ${python.stdin.end()}`);

  return JSON.parse(await readStream(python.stdout));
}

export function unreachable(x: never) {
  throw "impossible case reached";
}