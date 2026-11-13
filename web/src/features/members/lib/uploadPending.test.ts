// S6-F4 · US-148 y US-149: subir la foto y el documento firmado después de guardar al socio.
// Orden fijo: foto y luego documento; un fallo no detiene al otro archivo y se informa por separado.
import { ApiError } from "../../../core/api/errors";
import { uploadPending } from "./uploadPending";

const photo = new File(["p"], "p.png", { type: "image/png" });
const doc = new File(["d"], "d.pdf", { type: "application/pdf" });
const fail = (status: number, code: string) => new ApiError({ status, code, message: "Mensaje del api." });

describe("uploadPending", () => {
  it("sin archivos no sube nada", async () => {
    const upload = vi.fn();
    await expect(uploadPending(upload, { photo: null, consent: null })).resolves.toEqual([]);
    expect(upload).not.toHaveBeenCalled();
  });

  it("sube primero la foto y después el documento, cada uno con su kind", async () => {
    const upload = vi.fn<(kind: "photo" | "consent", file: File) => Promise<unknown>>().mockResolvedValue({});
    await expect(uploadPending(upload, { photo, consent: doc })).resolves.toEqual([]);
    expect(upload.mock.calls).toEqual([
      ["photo", photo],
      ["consent", doc],
    ]);
  });

  it("si la foto falla igual intenta el documento y devuelve el motivo de la foto", async () => {
    const upload = vi.fn<(kind: "photo" | "consent", file: File) => Promise<unknown>>().mockRejectedValueOnce(fail(413, "file_too_large")).mockResolvedValueOnce({});
    const failures = await uploadPending(upload, { photo, consent: doc });
    expect(failures).toEqual([{ kind: "photo", reason: "La foto supera 5 MB. Elige una de menos de 5 MB." }]);
    expect(upload).toHaveBeenCalledTimes(2);
  });

  it("devuelve los dos fallos en orden", async () => {
    const upload = vi.fn<(kind: "photo" | "consent", file: File) => Promise<unknown>>().mockRejectedValue(fail(422, "unsupported_type"));
    const failures = await uploadPending(upload, { photo, consent: doc });
    expect(failures.map((f) => f.kind)).toEqual(["photo", "consent"]);
  });
});
