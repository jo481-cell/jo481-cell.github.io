/* Ocarina de Hyrule Atlas. La scène affiche exclusivement le maillage de l'artiste. */
export function connect(exhibit, copy) {
  const stage = exhibit.querySelector("[data-stage]");
  const canvas = exhibit.querySelector("[data-canvas]");
  const poster = exhibit.querySelector("[data-poster]");
  const toggle = exhibit.querySelector("[data-activate]");
  const controls = exhibit.querySelector("[data-orbit]");
  const status = exhibit.querySelector("[data-status]");
  const toggleText = toggle.querySelector("[data-label]") || toggle;
  const originalLabel = toggleText.textContent.trim();
  const radians = degrees => degrees * Math.PI / 180;
  // Original Blender poster camera, expressed in glTF's Y-up coordinate system.
  const firstAngle = radians(Number(exhibit.dataset.angle || 28.811));
  const firstPitch = radians(Number(exhibit.dataset.pitch || 14.728));
  const roll = radians(Number(exhibit.dataset.roll || -38));
  const posterAspect = 1600 / 1000;
  const tanHorizontal = 18 / 75;
  const tanVertical = tanHorizontal / posterAspect;
  let angle = firstAngle;
  let elevation = firstPitch;
  let assetPromise;
  let state;
  let pointer;
  let frame = 0;
  let generation = 0;

  async function readModel() {
    const response = await fetch("/assets/models/ocarina-12-hole.glb", {credentials: "same-origin"});
    if (!response.ok) throw new Error("Model unavailable");
    const bytes = await response.arrayBuffer();
    const header = new DataView(bytes);
    if (header.getUint32(0, true) !== 0x46546c67 || header.getUint32(4, true) !== 2) {
      throw new Error("Format GLB non reconnu.");
    }
    const size = header.getUint32(12, true);
    const gltf = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 20, size)));
    const binStart = 28 + size;
    const primitive = gltf.meshes[0].primitives[0];
    const material = gltf.materials[primitive.material];
    const pbr = material.pbrMetallicRoughness;
    const coat = material.extensions?.KHR_materials_clearcoat;
    function accessor(index) {
      const item = gltf.accessors[index];
      const view = gltf.bufferViews[item.bufferView];
      const components = { VEC3: 3, SCALAR: 1 }[item.type];
      const ArrayType = { 5126: Float32Array, 5125: Uint32Array, 5123: Uint16Array }[item.componentType];
      if (!ArrayType || !components || view.byteStride) throw new Error("Attribut du modèle non pris en charge.");
      return new ArrayType(bytes, binStart + (view.byteOffset || 0) + (item.byteOffset || 0), item.count * components);
    }
    const bounds = gltf.accessors[primitive.attributes.POSITION];
    const center = bounds.min.map((min, i) => (bounds.max[i] + min) / 2);
    return {
      positions: accessor(primitive.attributes.POSITION), normals: accessor(primitive.attributes.NORMAL),
      indices: accessor(primitive.indices), center,
      color: pbr.baseColorFactor.slice(0, 3), roughness: pbr.roughnessFactor,
      coat: coat?.clearcoatFactor || 0, coatRoughness: coat?.clearcoatRoughnessFactor || 0
    };
  }
  function loadModel() {
    if (!assetPromise) assetPromise = readModel().catch(error => { assetPromise = undefined; throw error; });
    return assetPromise;
  }

  function cameraAxes(yaw, tilt) {
    const sy = Math.sin(yaw), cy = Math.cos(yaw), sp = Math.sin(tilt), cp = Math.cos(tilt);
    const sr = Math.sin(roll), cr = Math.cos(roll);
    return {
      right: [cy * cr - sy * sp * sr, cp * sr, -sy * cr - cy * sp * sr],
      up: [-sy * sp * cr - cy * sr, cp * cr, -cy * sp * cr + sy * sr],
      back: [sy * cp, sp, cy * cp]
    };
  }
  const dot = (x, y, z, axis) => x * axis[0] + y * axis[1] + z * axis[2];
  function fitToPoster(model) {
    const axes = cameraAxes(firstAngle, firstPitch);
    let distance = 0;
    for (let i = 0; i < model.positions.length; i += 3) {
      const x = model.positions[i] - model.center[0];
      const y = model.positions[i + 1] - model.center[1];
      const z = model.positions[i + 2] - model.center[2];
      const horizontal = Math.abs(dot(x, y, z, axes.right)) / tanHorizontal;
      const vertical = Math.abs(dot(x, y, z, axes.up)) / tanVertical;
      distance = Math.max(distance, dot(x, y, z, axes.back) + Math.max(horizontal, vertical) / .86);
    }
    return distance;
  }

  const shader = `
    struct Camera {
      right: vec4f, up: vec4f, back: vec4f, center: vec4f,
      base: vec4f, coat: vec4f
    }
    @group(0) @binding(0) var<uniform> camera: Camera;
    struct Surface {
      @builtin(position) clip: vec4f, @location(0) normal: vec3f, @location(1) toEye: vec3f
    }
    @vertex fn vertex(@location(0) position: vec3f, @location(1) normal: vec3f) -> Surface {
      let p = position - camera.center.xyz;
      let z = camera.back.w - dot(p, camera.back.xyz);
      let near = camera.back.w * .08;
      let far = camera.back.w * 2.;
      var s: Surface;
      s.clip = vec4f(dot(p, camera.right.xyz) * camera.right.w,
                     dot(p, camera.up.xyz) * camera.up.w,
                     (z - near) * far / (far - near), z);
      s.normal = normal;
      s.toEye = camera.back.xyz * camera.back.w - p;
      return s;
    }
    fn softbox(r: vec3f, direction: vec3f, radius: f32, rough: f32) -> f32 {
      let edge = .02 + .055 * rough;
      return smoothstep(radius - edge, radius + edge, dot(r, direction));
    }
    @fragment fn fragment(s: Surface) -> @location(0) vec4f {
      let n = normalize(s.normal);
      let v = normalize(s.toEye);
      let reflected = reflect(-v, n);
      let key = normalize(vec3f(-.12,.22,.18));
      let fill = normalize(vec3f(.14,.04,.10));
      let rim = normalize(vec3f(.10,.18,-.12));
      let warm = vec3f(1.,.87,.74);
      let cool = vec3f(.70,.84,1.);
      let ivory = vec3f(1.,.93,.82);
      let light = vec3f(.22,.27,.36) + 1.55 * max(dot(n,key),0.) * warm
        + .85 * max(dot(n,fill),0.) * cool + .85 * max(dot(n,rim),0.) * ivory;
      let glaze = camera.coat.x;
      let roughness = mix(camera.base.w, camera.coat.y, glaze);
      let reflection = softbox(reflected,key,.975,roughness)*warm
        + .56*softbox(reflected,fill,.949,roughness)*cool
        + .83*softbox(reflected,rim,.977,roughness)*ivory;
      let fresnel = .04 + .96*pow(1. - max(dot(n,v),0.), 5.);
      let linear = camera.base.rgb*light + (.12 + .32*glaze + fresnel)*reflection;
      let color = pow(clamp(linear / (vec3f(1.) + linear*.25), vec3f(0.), vec3f(1.)), vec3f(1./2.2));
      return vec4f(color,1.);
    }`;

  async function prepare(device, model) {
    const context = canvas.getContext("webgpu");
    if (!context) throw new Error("Le contexte WebGPU est indisponible.");
    const format = navigator.gpu.getPreferredCanvasFormat();
    const module = device.createShaderModule({ code: shader });
    const attribute = shaderLocation => ({
      arrayStride: 12, attributes: [{ shaderLocation, offset: 0, format: "float32x3" }]
    });
    const pipeline = await device.createRenderPipelineAsync({
      layout: "auto",
      vertex: { module, entryPoint: "vertex", buffers: [attribute(0), attribute(1)] },
      fragment: { module, entryPoint: "fragment", targets: [{ format }] },
      primitive: { topology: "triangle-list", cullMode: "back" },
      multisample: { count: 4 },
      depthStencil: { format: "depth24plus", depthWriteEnabled: true, depthCompare: "less" }
    });
    function upload(data, usage) {
      const size = Math.ceil(data.byteLength / 4) * 4;
      const buffer = device.createBuffer({ size, usage, mappedAtCreation: true });
      new Uint8Array(buffer.getMappedRange()).set(new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
      buffer.unmap();
      return buffer;
    }
    const uniform = device.createBuffer({ size: 96, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    const group = device.createBindGroup({
      layout: pipeline.getBindGroupLayout(0), entries: [{ binding: 0, resource: { buffer: uniform } }]
    });
    return {
      device, context, format, pipeline, group, uniform, distance: fitToPoster(model),
      position: upload(model.positions, GPUBufferUsage.VERTEX), normal: upload(model.normals, GPUBufferUsage.VERTEX),
      index: upload(model.indices, GPUBufferUsage.INDEX), count: model.indices.length,
      indexFormat: model.indices instanceof Uint32Array ? "uint32" : "uint16",
      center: model.center, color: model.color, roughness: model.roughness,
      coat: model.coat, coatRoughness: model.coatRoughness
    };
  }

  function draw() {
    frame = 0;
    if (!state) return;
    const s = state;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const pixelRatio = Math.min(devicePixelRatio || 1, 2, 1900 / Math.max(rect.width, rect.height));
    const w = Math.max(1, Math.round(rect.width * pixelRatio)), h = Math.max(1, Math.round(rect.height * pixelRatio));
    if (s.width !== w || s.height !== h) {
      s.width = canvas.width = w;
      s.height = canvas.height = h;
      s.context.configure({ device: s.device, format: s.format, alphaMode: "premultiplied" });
      s.depth?.destroy(); s.colorTarget?.destroy();
      const attachment = format => s.device.createTexture({
        size: [w, h], sampleCount: 4, format, usage: GPUTextureUsage.RENDER_ATTACHMENT
      });
      s.depth = attachment("depth24plus");
      s.colorTarget = attachment(s.format);
    }
    const aspect = w / h;
    const axes = cameraAxes(angle, elevation);
    s.device.queue.writeBuffer(s.uniform, 0, new Float32Array([
      ...axes.right, 1 / (tanHorizontal * Math.max(1, aspect / posterAspect)),
      ...axes.up, 1 / (tanVertical * Math.max(1, posterAspect / aspect)),
      ...axes.back, s.distance, ...s.center, 0, ...s.color, s.roughness, s.coat, s.coatRoughness, 0, 0
    ]));
    const encoder = s.device.createCommandEncoder();
    const pass = encoder.beginRenderPass({
      colorAttachments: [{
        view: s.colorTarget.createView(), resolveTarget: s.context.getCurrentTexture().createView(),
        clearValue: { r: 0, g: 0, b: 0, a: 0 }, loadOp: "clear", storeOp: "discard"
      }],
      depthStencilAttachment: {
        view: s.depth.createView(), depthClearValue: 1, depthLoadOp: "clear", depthStoreOp: "discard"
      }
    });
    pass.setPipeline(s.pipeline); pass.setBindGroup(0, s.group);
    pass.setVertexBuffer(0, s.position); pass.setVertexBuffer(1, s.normal);
    pass.setIndexBuffer(s.index, s.indexFormat); pass.drawIndexed(s.count);
    pass.end(); s.device.queue.submit([encoder.finish()]);
  }
  function schedule() { if (state && !frame) frame = requestAnimationFrame(draw); }
  function stop(message = "") {
    ++generation;
    cancelAnimationFrame(frame); frame = 0; pointer = undefined;
    const previous = state;
    state = undefined;
    previous?.context.unconfigure();
    previous?.device.destroy();
    canvas.hidden = true; poster.hidden = false; controls.hidden = true;
    exhibit.dataset.render = "poster";
    toggle.disabled = false; toggleText.textContent = originalLabel;
    toggle.setAttribute("aria-pressed", "false"); status.textContent = message;
  }
  async function start() {
    if (state) { stop(); return; }
    const request = ++generation;
    let device;
    toggle.disabled = true; toggleText.textContent = copy.loading;
    status.textContent = copy.loading;
    try {
      const adapter = await navigator.gpu?.requestAdapter();
      if (request !== generation) return;
      if (!adapter) throw new Error("Aucun adaptateur WebGPU.");
      const model = await loadModel();
      if (request !== generation) return;
      device = await adapter.requestDevice();
      if (request !== generation) { device.destroy(); return; }
      const live = await prepare(device, model);
      if (request !== generation) { device.destroy(); return; }
      state = live; angle = firstAngle; elevation = firstPitch;
      device.lost.then(() => {
        if (state === live) stop(copy.fallback);
      });
      device.addEventListener("uncapturederror", event => {
        if (state === live) { console.warn(event.error.message); stop(copy.fallback); }
      });
      canvas.hidden = false; controls.hidden = false;
      // Keep the poster's layout box until the first frame is ready.
      exhibit.dataset.render = "live";
      draw();
      poster.hidden = true;
      schedule();
      toggleText.textContent = copy.still;
      toggle.setAttribute("aria-pressed", "true");
      status.textContent = copy.hint;
    } catch (error) {
      device?.destroy();
      if (request === generation) {
        console.info("Ocarina", error.message);
        stop(copy.fallback);
      }
    } finally { if (request === generation) toggle.disabled = false; }
  }
  function turn(steps) { angle += steps * Math.PI / 12; schedule(); }
  const limitElevation = value => Math.max(-Math.PI * .49, Math.min(Math.PI * .49, value));
  function tilt(steps) { elevation = limitElevation(elevation + steps * Math.PI / 12); schedule(); }
  canvas.addEventListener("pointerdown", event => {
    if (!state || pointer || event.button !== 0) return;
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, angle, elevation };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (pointer?.id !== event.pointerId) return;
    angle = pointer.angle - (event.clientX - pointer.x) / Math.max(1, canvas.clientWidth) * Math.PI * 2;
    elevation = limitElevation(pointer.elevation + (event.clientY - pointer.y) / Math.max(1, canvas.clientHeight) * Math.PI);
    schedule();
  });
  canvas.addEventListener("lostpointercapture", () => { pointer = null; });
  canvas.addEventListener("keydown", event => {
    switch (event.key) {
      case "ArrowRight": turn(1); break;
      case "ArrowLeft": turn(-1); break;
      case "ArrowUp": tilt(1); break;
      case "ArrowDown": tilt(-1); break;
      default: return;
    }
    event.preventDefault();
  });
  controls.querySelectorAll("[data-turn]").forEach(button => {
    button.addEventListener("click", () => turn(Number(button.dataset.turn)));
  });
  controls.querySelectorAll("[data-tilt]").forEach(button => {
    button.addEventListener("click", () => tilt(Number(button.dataset.tilt)));
  });
  controls.querySelector("[data-reset]").addEventListener("click", () => {
    angle = firstAngle; elevation = firstPitch; schedule();
  });
  if ("ResizeObserver" in window) new ResizeObserver(schedule).observe(stage);
  else window.addEventListener("resize", schedule);
  window.addEventListener("pagehide", () => stop());
  exhibit.addEventListener("relique:fermer", () => stop());
  toggle.addEventListener("click", start);
  toggle.setAttribute("aria-pressed", "false");
  toggle.hidden = false;
  exhibit.dataset.render = "poster";
}
