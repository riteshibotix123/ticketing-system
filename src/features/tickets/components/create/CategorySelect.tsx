import { useField } from '@/components/common/FormField';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Category } from '@/types/domain';

/** Category select, dependent on the chosen department (spec 9.5). */
export function CategorySelect({
  value,
  onChange,
  categories,
  disabled,
}: {
  value: string;
  onChange: (categoryId: string) => void;
  categories: Category[];
  disabled?: boolean;
}) {
  const field = useField();

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        id={field?.id}
        className="w-full"
        aria-invalid={field?.invalid || undefined}
        aria-describedby={field?.describedBy}
      >
        <SelectValue placeholder="Select a category" />
      </SelectTrigger>
      <SelectContent>
        {categories.map((category) => (
          <SelectItem key={category.id} value={category.id}>
            {category.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
