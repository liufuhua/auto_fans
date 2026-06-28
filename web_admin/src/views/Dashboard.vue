<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">控制台</h1>
        <p class="page-subtitle">查看当天任务、设备和执行结果概览。</p>
      </div>
    </div>

    <el-row :gutter="14">
      <el-col :span="6">
        <div class="metric-card">
          <span class="metric-label">今日任务</span>
          <strong>0</strong>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <span class="metric-label">在线设备</span>
          <strong>0 / 8</strong>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <span class="metric-label">成功评论</span>
          <strong>0</strong>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <span class="metric-label">待复检</span>
          <strong>0</strong>
        </div>
      </el-col>
    </el-row>

    <div class="content-panel">
      <el-empty description="后端 API 接入后展示实时任务进度" />
    </div>
  </section>
</template>

<style scoped>
.metric-card {
  display: flex;
  min-height: 88px;
  flex-direction: column;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 16px;
}

.metric-label {
  color: #6b7280;
  font-size: 13px;
}

.metric-card strong {
  margin-top: 8px;
  color: #111827;
  font-size: 26px;
  line-height: 1;
}
</style>
