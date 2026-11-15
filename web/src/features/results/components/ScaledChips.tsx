// S8-F4 · US-170 (L-2): «¿Qué escaló?» (Resultados_Registro.html). Un chip por movimiento del WOD; llenan `scaled_movement_ids`
// (ids de movimientos del WOD, nunca texto libre). Aparece al tocar «Escalado».
// DESIGN-GAP: «+ otro» (texto libre) no existe: el contrato solo admite movimientos del WOD.
import { Chips } from "../../../shared/ui/Chips";

export interface ScaledMovement {
  movement_id: string;
  movement_name: string;
}

export interface ScaledChipsProps {
  movements: readonly ScaledMovement[];
  value: readonly string[];
  onChange: (ids: string[]) => void;
}

export function ScaledChips({ movements, value, onChange }: ScaledChipsProps) {
  if (movements.length === 0) return null;
  return (
    <Chips
      label="¿Qué escaló?"
      mode="multiple"
      options={movements.map((movement) => ({ value: movement.movement_id, label: movement.movement_name }))}
      value={value}
      onChange={onChange}
    />
  );
}
