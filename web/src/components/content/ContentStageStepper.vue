<script setup>
import { Check } from 'lucide-vue-next'

defineProps({
  current: { type: Number, default: 1 }
})

defineEmits(['select'])

const steps = [
  { index: 1, label: '业务素材', description: '形成统一简报' },
  { index: 2, label: '创作策略', description: '锁定公式组合' },
  { index: 3, label: '内容生成', description: '人工选择标题' },
  { index: 4, label: '审核交付', description: '编辑、审核与版本' }
]
</script>

<template>
  <ol class="content-stage-stepper" aria-label="内容生产阶段">
    <li
      v-for="step in steps"
      :key="step.index"
      :class="{ active: current === step.index, completed: current > step.index }"
    >
      <button
        type="button"
        :disabled="step.index > current"
        @click="$emit('select', step.index)"
      >
        <span class="step-index">
          <Check v-if="current > step.index" :size="15" />
          <template v-else>{{ step.index }}</template>
        </span>
        <span class="step-copy">
          <strong>{{ step.label }}</strong>
          <small>{{ step.description }}</small>
        </span>
      </button>
    </li>
  </ol>
</template>

<style scoped lang="less">
.content-stage-stepper {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);

  li {
    min-width: 0;
    border-right: 1px solid var(--gray-150);

    &:last-child {
      border-right: 0;
    }
  }

  button {
    width: 100%;
    min-height: 68px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border: 0;
    background: transparent;
    color: var(--color-text-secondary);
    text-align: left;
    cursor: pointer;

    &:disabled {
      cursor: default;
    }
  }

  .active button {
    background: var(--main-30);
    color: var(--main-700);
  }

  .completed button {
    color: var(--color-text);
  }

  .step-index {
    width: 28px;
    height: 28px;
    flex: 0 0 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--gray-200);
    border-radius: 50%;
    font-weight: 600;
  }

  .active .step-index,
  .completed .step-index {
    border-color: var(--main-color);
    background: var(--main-color);
    color: var(--gray-0);
  }

  .step-copy {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong {
      font-size: 14px;
      font-weight: 600;
    }

    small {
      color: var(--color-text-tertiary);
      font-size: 12px;
    }
  }
}

@media (max-width: 800px) {
  .content-stage-stepper {
    grid-template-columns: repeat(4, 1fr);

    button {
      min-height: 52px;
      justify-content: center;
      padding: 10px 6px;
    }

    .step-copy small {
      display: none;
    }

    .step-copy strong {
      font-size: 12px;
    }
  }
}

@media (max-width: 480px) {
  .content-stage-stepper .step-index {
    display: none;
  }
}
</style>
