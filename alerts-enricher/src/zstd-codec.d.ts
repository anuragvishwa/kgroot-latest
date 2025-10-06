declare module 'zstd-codec' {
  interface ZstdInstance {
    compress(data: Buffer | Uint8Array): Uint8Array;
    decompress(data: Buffer | Uint8Array): Uint8Array;
  }

  function run(callback: (zstd: ZstdInstance) => void): void;

  export default { run };
}
