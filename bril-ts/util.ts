import {Stream} from "stream";
import Socket = NodeJS.Socket;

/**
 * Read all the data from stdin as a string.
 */
export function readStdin(): Promise<string> {
  return readSocket(process.stdin);
}

export function readSocket(socket: Socket): Promise<string> {
  return new Promise((resolve, reject) => {
    let chunks: string[] = [];
    socket.on("data", function (chunk: string) {
      chunks.push(chunk);
    }).on("end", function () {
      resolve(chunks.join(""))
    }).setEncoding("utf8");
  });
}

export function unreachable(x: never) {
  throw "impossible case reached";
}